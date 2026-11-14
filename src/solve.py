"""
solve.py  —  Persona A, tarea A8: resolver el modelo y guardar resultados.

Hace tres cosas:
1. Construye el modelo (model.py) para un escenario y un modo.
2. Lo resuelve con Gurobi (o HiGHS si no hay Gurobi) y mide tiempos, gap y
   tamaño del modelo.
3. Guarda los resultados en results/<nombre>/ :
     x.csv  (j, k, t, x)      equipos en marcha (solo los distintos de 0)
     s.csv  (p, d, s)         nieve en cada sector al final del día
     b.csv  (d, b)            agua en la balsa
     y.csv  (p, d, y)         pistas abiertas            (si existe la parte de B)
     u.csv, n.csv             inversión                  (modo investment)
     h.csv  (d, h)            km de compromiso incumplidos
     summary.json             estado, objetivo, gap, tiempos, tamaño, opciones

Plan de escalado (sección 3.5 del plan, comentario C4 del profesor):
  --days N      usa solo los N primeros días del horizonte (instancias pequeñas)
  --relax-x     x continua en vez de entera (si el horizonte completo es lento;
                con muchos equipos por posición el redondeo apenas cambia nada)

Datos: usa load_data.py (tarea B9 de Adri) si existe; si no, el cargador de
prueba de test_model_a.py. Objetivo: el de constraints_b.py si existe; si no,
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


def load(scenario: str) -> dict:
    try:
        from load_data import load_data            # tarea B9 (Persona B)
        return load_data(scenario)
    except ImportError:
        from test_model_a import load_test_data
        print("AVISO: no hay load_data.py -> cargador de prueba (precios provisionales)")
        return load_test_data(scenario)


def restrict_days(data: dict, n_days: int) -> dict:
    """Recorta el horizonte a los n_days primeros días (para escalar)."""
    D = [d for d in data["D"] if d < n_days]
    T = [t for d in D for t in data["Td"][d]]
    data = dict(data, D=D, T=T, DC=[d for d in data["DC"] if d in D],
                Td={d: data["Td"][d] for d in D})
    return data


def add_test_objective(m, data) -> None:
    print("AVISO: no hay función objetivo de B -> objetivo de prueba "
          "(máxima nieve el 6 dic - LAMBDA * coste)")
    key = KEY_DAY if KEY_DAY in data["D"] else max(data["D"])
    cost = sum(data["PI"][t] * data["E"][j, k, t] * m.x[j, k, t]
               for j in m.J for k in m.K for t in m.T)
    m.obj = pyo.Objective(expr=sum(m.s[p, key] for p in m.P) - LAMBDA * cost,
                          sense=pyo.maximize)


def model_size(m) -> dict:
    vars_ = [v for v in m.component_data_objects(pyo.Var, active=True) if not v.fixed]
    return {"variables": len(vars_),
            "enteras_o_binarias": sum(not v.is_continuous() for v in vars_),
            "restricciones": sum(1 for _ in m.component_data_objects(pyo.Constraint, active=True))}


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

    t0 = time.perf_counter()
    data = load(args.scenario)
    if args.days:
        data = restrict_days(data, args.days)
    m = build_model(data, mode=args.mode)
    if args.relax_x:
        for v in m.x.values():
            v.domain = pyo.NonNegativeReals
    if not hasattr(m, "obj"):
        add_test_objective(m, data)
    t_build = time.perf_counter() - t0

    name, solver = pick_solver(args.solver)
    if "gurobi" in name:
        solver.options.update({"MIPGap": args.gap, "TimeLimit": args.time_limit})
    else:
        solver.options.update({"mip_rel_gap": args.gap, "time_limit": args.time_limit})

    t1 = time.perf_counter()
    res = solver.solve(m)
    t_solve = time.perf_counter() - t1

    obj = pyo.value(m.obj)
    try:                                       # cota del solver -> gap real
        lb, ub = res.problem.lower_bound, res.problem.upper_bound
        gap = abs(ub - lb) / max(abs(ub), abs(lb), 1e-9)
    except Exception:
        gap = None

    summary = {
        "escenario": args.scenario, "modo": args.mode, "solver": name,
        "dias": len(data["D"]), "x_continua": args.relax_x,
        "estado": str(res.solver.termination_condition),
        "objetivo": round(obj, 2), "gap": None if gap is None else round(gap, 5),
        "t_construccion_s": round(t_build, 1), "t_resolucion_s": round(t_solve, 1),
        **model_size(m),
    }
    run = args.name or f"{args.scenario}_{args.mode}" + (f"_{args.days}d" if args.days else "") \
        + ("_relax" if args.relax_x else "")
    out = RESULTS / run
    export(m, out)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                                      encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Resultados en {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
