"""
solve.py  —  Persona A, tarea A8: resolver el modelo y guardar resultados.

1. Construye el modelo (model.py) para un escenario y un modo.
2. Lo resuelve con Gurobi (o HiGHS si no hay Gurobi) y mide tiempos, gap y
   tamaño del modelo.
3. Guarda en results/<nombre>/ un CSV por variable (x solo los distintos de 0)
   y summary.json con estado, objetivo, gap, tiempos, tamaño e indicadores.

La función solve_scenario() es la que usan los experimentos (src/experiments/).

Plan de escalado (sección 3.5 del plan, comentario C4 del profesor):
  --days N      solo los N primeros días del horizonte
  --relax-x     x continua en vez de entera

Datos: load_data.py (tarea B9) si existe; si no, el cargador de prueba de
test_model_a.py. Objetivo: el de constraints_b.py si hay datos para él; si no,
el objetivo de prueba (máxima nieve el 6 de diciembre) y avisa.

Uso:
  python src/solve.py --scenario normal --mode operation
  python src/solve.py --scenario calida --mode investment --days 21
"""

import argparse
import json
import time
from pathlib import Path

import pandas as pd
import pyomo.environ as pyo

from model import build_model
from test_model_a import KEY_DAY, LAMBDA, pick_solver

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"


# ----------------------------------------------------------------------------
# Datos
# ----------------------------------------------------------------------------
def load(scenario: str, quiet: bool = False) -> dict:
    try:
        from load_data import load_data            # tarea B9 (Persona B)
        return load_data(scenario)
    except ImportError:
        from test_model_a import load_test_data
        if not quiet:
            print("AVISO: no hay load_data.py -> cargador de prueba (precios provisionales)")
        return load_test_data(scenario)


def restrict_days(data: dict, n_days: int) -> dict:
    """Recorta el horizonte a los n_days primeros días (para escalar)."""
    D = [d for d in data["D"] if d < n_days]
    T = [t for d in D for t in data["Td"][d]]
    return dict(data, D=D, T=T, DC=[d for d in data["DC"] if d in D],
                Td={d: data["Td"][d] for d in D})


# ----------------------------------------------------------------------------
# Modelo
# ----------------------------------------------------------------------------
def add_test_objective(m, data, quiet: bool = False) -> None:
    if not quiet:
        print("AVISO: sin objetivo de B -> objetivo de prueba "
              "(máxima nieve el 6 dic - LAMBDA * coste)")
    key = KEY_DAY if KEY_DAY in data["D"] else max(data["D"])
    cost = sum(data["PI"][t] * data["E"][j, k, t] * m.x[j, k, t]
               for j in m.J for k in m.K for t in m.T)
    m.ELECTRICITY = pyo.Expression(expr=cost)
    m.obj = pyo.Objective(expr=sum(m.s[p, key] for p in m.P) - LAMBDA * cost,
                          sense=pyo.maximize)


def model_size(m) -> dict:
    vars_ = [v for v in m.component_data_objects(pyo.Var, active=True) if not v.fixed]
    return {"variables": len(vars_),
            "enteras_o_binarias": sum(not v.is_continuous() for v in vars_),
            "restricciones": sum(1 for _ in m.component_data_objects(pyo.Constraint, active=True))}


def prepare(data: dict, mode: str = "operation", relax_x: bool = False, quiet: bool = False):
    """Construye el modelo listo para resolver (con objetivo)."""
    m = build_model(data, mode=mode)
    if relax_x:
        for v in m.x.values():
            v.domain = pyo.NonNegativeReals
    if not hasattr(m, "obj"):
        add_test_objective(m, data, quiet)
    return m


def run_solver(m, solver_name=None, gap=0.01, time_limit=600, quiet=False):
    """Resuelve y devuelve (estado, gap, segundos, nombre del solver)."""
    name, solver = pick_solver(solver_name) if not quiet else _pick_quiet(solver_name)
    if "gurobi" in name:
        solver.options.update({"MIPGap": gap, "TimeLimit": time_limit})
    else:
        solver.options.update({"mip_rel_gap": gap, "time_limit": time_limit})
    t = time.perf_counter()
    try:
        res = solver.solve(m, load_solutions=True)
    except RuntimeError as e:                      # HiGHS sin solución factible
        return "sin_solucion", None, time.perf_counter() - t, name
    secs = time.perf_counter() - t
    try:
        lb, ub = res.problem.lower_bound, res.problem.upper_bound
        g = abs(ub - lb) / max(abs(ub), abs(lb), 1e-9)
    except Exception:
        g = None
    return str(res.solver.termination_condition), g, secs, name


_SOLVER_CACHE = {}


def _pick_quiet(solver_name):
    if solver_name not in _SOLVER_CACHE:
        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()):
            _SOLVER_CACHE[solver_name] = pick_solver(solver_name)
    return _SOLVER_CACHE[solver_name]


# ----------------------------------------------------------------------------
# Indicadores (los mismos para todos los experimentos)
# ----------------------------------------------------------------------------
def water_used(m, data, t=None) -> float:
    T = [t] if t is not None else list(m.T)
    return sum(data["PHI"][k] * data["G"][j, k, tt] * (pyo.value(m.x[j, k, tt]) or 0)
               for j in m.J for k in m.K for tt in T)


def kpis(m, data) -> dict:
    v = pyo.value
    out = {"objetivo": v(m.obj)}
    for name in ["REVENUE", "ELECTRICITY", "INVESTMENT", "PENALTY"]:
        if hasattr(m, name):
            out[name.lower()] = v(getattr(m, name))
    if "revenue" in out:     # beneficio "de verdad": sin la penalización (que es un recurso del modelo)
        out["beneficio_real"] = out["revenue"] - out.get("electricity", 0) - out.get("investment", 0)
    used = water_used(m, data)
    out["agua_usada_m3"] = used
    out["agua_pct_W"] = 100 * used / data["W"]
    out["bloques_caudal_max"] = sum(water_used(m, data, t) > 0.99 * data["Q_MAX"] for t in m.T)
    out["nieve_producida_m3"] = sum(data["G"][j, k, t] * (v(m.x[j, k, t]) or 0)
                                    for j in m.J for k in m.K for t in m.T)
    if "LEN" in data and hasattr(m, "R3a"):        # solo con la parte de B
        y = {(p, d): round(m.y[p, d].value or 0) for p in m.P for d in m.D}
        out["sector_dias_abiertos"] = sum(y.values())
        out["km_dia_medio"] = sum(data["LEN"][p] * y[p, d] for p, d in y) / len(m.D)
        out["km_incumplidos_total"] = sum(v(m.h[d]) for d in m.DC)
        out["dias_clave_cumplidos"] = sum(v(m.h[d]) < 0.01 for d in m.DC)
    else:
        key = KEY_DAY if KEY_DAY in m.D else max(m.D)
        out["nieve_dia_clave_m3"] = sum(v(m.s[p, key]) for p in m.P)
        out["sectores_con_V_dia_clave"] = sum(v(m.s[p, key]) >= data["V"][p] - 1e-6
                                             for p in m.P if p in data["Jp"])
    if not m.u[next(iter(m.JN))].fixed:
        out["posiciones_nuevas"] = sum(round(m.u[j].value or 0) for j in m.JN)
        out["equipos_nuevos"] = {k: sum(round(m.n[j, k].value or 0) for j in m.JN) for k in m.K}
    return {k: (round(x, 2) if isinstance(x, float) else x) for k, x in out.items()}


def export(m, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)

    def dump(var, cols, name, only_nonzero=False):
        rows = [(*(idx if isinstance(idx, tuple) else (idx,)), pyo.value(v))
                for idx, v in var.items() if v.value is not None]
        df = pd.DataFrame(rows, columns=cols).round(4)
        if only_nonzero:
            df = df[df[cols[-1]].abs() > 1e-6]
        df.to_csv(out / f"{name}.csv", index=False)

    dump(m.x, ["j", "k", "t", "x"], "x", only_nonzero=True)
    dump(m.s, ["p", "d", "s"], "s")
    dump(m.b, ["d", "b"], "b")
    dump(m.y, ["p", "d", "y"], "y")
    dump(m.u, ["j", "u"], "u")
    dump(m.n, ["j", "k", "n"], "n", only_nonzero=True)
    dump(m.h, ["d", "h"], "h")


# ----------------------------------------------------------------------------
def solve_scenario(scenario="normal", mode="operation", data=None, eps=None,
                   solver=None, gap=0.01, time_limit=600, relax_x=False, days=None,
                   name=None, save=True, quiet=False):
    """Construye, resuelve y (opcional) guarda un caso. Devuelve (summary, m, data).
    data: diccionario ya preparado (los experimentos lo modifican antes)."""
    t0 = time.perf_counter()
    if data is None:
        data = load(scenario, quiet)
    if days:
        data = restrict_days(data, days)
    m = prepare(data, mode, relax_x, quiet)
    if eps is not None:
        m.W_EPS = min(eps, data["W"])
    t_build = time.perf_counter() - t0

    status, g, t_solve, solver_name = run_solver(m, solver, gap, time_limit, quiet)
    summary = {"escenario": scenario, "modo": mode, "solver": solver_name,
               "dias": len(data["D"]), "x_continua": relax_x, "estado": status,
               "gap": None if g is None else round(g, 5),
               "t_construccion_s": round(t_build, 1), "t_resolucion_s": round(t_solve, 1),
               **model_size(m)}
    if status != "sin_solucion":
        summary.update(kpis(m, data))
    if save and status != "sin_solucion":
        run = name or f"{scenario}_{mode}" + (f"_{days}d" if days else "") \
            + ("_relax" if relax_x else "")
        out = RESULTS / run
        export(m, out)
        (out / "summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        summary["carpeta"] = str(out.relative_to(ROOT))
    return summary, m, data


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="normal")
    ap.add_argument("--mode", default="operation", choices=["operation", "investment"])
    ap.add_argument("--solver", default=None)
    ap.add_argument("--days", type=int, default=None)
    ap.add_argument("--relax-x", action="store_true")
    ap.add_argument("--gap", type=float, default=0.01)
    ap.add_argument("--time-limit", type=int, default=600)
    ap.add_argument("--name", default=None, help="carpeta de resultados")
    args = ap.parse_args()

    summary, _, _ = solve_scenario(args.scenario, args.mode, solver=args.solver,
                                   gap=args.gap, time_limit=args.time_limit,
                                   relax_x=args.relax_x, days=args.days, name=args.name)
    print(json.dumps(summary, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
