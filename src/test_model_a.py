"""
test_model_a.py  —  Persona A: prueba de las restricciones R1, R2, R5, R6, R7
SIN la parte de Adri (función objetivo, R3, R4, R8, R9).

Objetivo PROVISIONAL (solo para probar):
    max  Σ_p s_{p, 6 dic}  -  LAMBDA · coste eléctrico
"¿Cuánta nieve puede tener la estación en pista el 6 de diciembre?" — con una
pequeña penalización del coste para que elija las horas baratas.

Datos PROVISIONALES de Adri que aún no existen:
    PI_t  precio de la luz: 0,08 €/kWh de 0 a 6 h, 0,20 de 18 a 21 h, 0,15 el resto
    Z     si pistas.csv no tiene area_m2 -> 0 (sin nieve natural)
    S0    si la columna está vacía -> 0

Uso:   python src/test_model_a.py --scenario normal
       Elige solo el solver: Gurobi (gurobipy) si está instalado y, si no,
       HiGHS (pip install highspy). Se puede forzar con --solver.
"""

import argparse
from pathlib import Path

import pandas as pd
import pyomo.environ as pyo

from model import build_model

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
KEY_DAY = 21            # d = 21 -> 6 de diciembre (d = 0 es el 15 de noviembre)
LAMBDA = 0.01           # m³ de nieve que "vale" 1 € en el objetivo de prueba


def read_yaml_simple(path: Path) -> dict:
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            k, v = line.split(":")
            out[k.strip()] = float(v)
    return out


def load_test_data(scenario: str) -> dict:
    periods = pd.read_csv(ROOT / "data" / "interim" / "periods.csv")
    prod = pd.read_csv(PROC / "scenarios" / scenario / "production.csv")
    snow = pd.read_csv(PROC / "scenarios" / scenario / "snow.csv").fillna({"Z": 0.0})
    pistas = pd.read_csv(PROC / "pistas.csv")
    pos = pd.read_csv(PROC / "positions.csv")
    we = read_yaml_simple(PROC / "water_energy.yaml")
    inflow = pd.read_csv(PROC / "inflow.csv")

    D = sorted(periods["d"].unique().tolist())
    T = periods["t"].tolist()
    hour = dict(zip(periods["t"], periods["hour_start"]))
    PI = {t: 0.08 if hour[t] < 6 else 0.20 if 18 <= hour[t] < 21 else 0.15 for t in T}

    data = {
        "P": pistas["p"].tolist(),
        "J": pos["j"].tolist(),
        "JE": pos.loc[pos["type"] == "E", "j"].tolist(),
        "JN": pos.loc[pos["type"] == "N", "j"].tolist(),
        "K": ["FAN", "AW"],
        "D": D, "DC": [KEY_DAY], "T": T,
        "Td": periods.groupby("d")["t"].apply(list).to_dict(),
        "Jp": pos.groupby("p")["j"].apply(list).to_dict(),
        "G": {(r.j, r.k, r.t): r.G for r in prod.itertuples()},
        "A": {(r.j, r.k, r.t): r.A for r in prod.itertuples()},
        "E": {(r.j, r.k, r.t): r.E for r in prod.itertuples()},
        "PHI": {"FAN": we["PHI_FAN"], "AW": we["PHI_AW"]},
        "DELTA": {(r.p, r.d): r.Delta for r in snow.itertuples()},
        "Z": {(r.p, r.d): r.Z for r in snow.itertuples()},
        "S0": dict(zip(pistas["p"], pistas["S0"].fillna(0.0))),
        "B_MAX": we["B_MAX"], "B0": we["B0"], "W": we["W"],
        "Q_MAX": we["Q_MAX"], "E_MAX": we["E_MAX"],
        "I": dict(zip(inflow["d"], inflow["I"])),
        "N0": {**{(r.j, "FAN"): r.N0_FAN for r in pos.itertuples()},
               **{(r.j, "AW"): r.N0_AW for r in pos.itertuples()}},
        "PI": PI,                                            # PROVISIONAL
        "V": dict(zip(pistas["p"], pistas["V"])),
    }
    return data


SOLVERS = ["gurobi", "gurobi_direct", "appsi_highs"]   # Gurobi (como en clase); HiGHS solo de reserva


def pick_solver(name: str | None):
    """Devuelve el primer solver disponible (o el pedido con --solver)."""
    for cand in ([name] if name else SOLVERS):
        solver = pyo.SolverFactory(cand)
        try:
            if solver.available(exception_flag=False):
                print(f"Solver: {cand}")
                return cand, solver
        except Exception:
            pass
    raise RuntimeError("No hay solver MILP disponible: instala gurobipy o highspy "
                       "(pip install highspy)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="normal")
    ap.add_argument("--solver", default=None)
    args = ap.parse_args()

    data = load_test_data(args.scenario)
    m = build_model(data, mode="operation")

    cost = sum(data["PI"][t] * data["E"][j, k, t] * m.x[j, k, t]
               for j in m.J for k in m.K for t in m.T)
    m.obj = pyo.Objective(expr=sum(m.s[p, KEY_DAY] for p in m.P) - LAMBDA * cost,
                          sense=pyo.maximize)

    name, solver = pick_solver(args.solver)
    if "gurobi" in name:
        solver.options.update({"MIPGap": 0.01, "TimeLimit": 300})
    else:
        solver.options.update({"mip_rel_gap": 0.01, "time_limit": 300})
    res = solver.solve(m)
    print("Estado:", res.solver.termination_condition)

    # ------------------------- Comprobaciones -------------------------------
    D, T = data["D"], data["T"]
    water = lambda t: sum(data["PHI"][k] * data["G"][j, k, t] * pyo.value(m.x[j, k, t])
                          for j in m.J for k in m.K)
    used = sum(water(t) for t in T)
    flow_binding = sum(water(t) > 0.99 * data["Q_MAX"] for t in T)
    snow_key = {p: pyo.value(m.s[p, KEY_DAY]) for p in m.P}

    print(f"\nNieve en pista el 6 dic: {sum(snow_key.values()):,.0f} m³ "
          f"(abrir todos los sectores existentes pediría {sum(data['V'][p] for p in data['Jp'] if any(j in data['JE'] for j in data['Jp'][p])):,.0f} m³)")
    print(f"Agua usada: {used:,.0f} m³ de W = {data['W']:,.0f}")
    print(f"Bloques con el caudal al máximo (R7): {flow_binding} de {len(T)}")
    print(f"Coste eléctrico: {pyo.value(cost):,.0f} €")
    print(f"Balsa mínima: {min(pyo.value(m.b[d]) for d in D):,.0f} m³")

    hours = pd.read_csv(ROOT / "data" / "interim" / "periods.csv").set_index("t")["hour_start"]
    by_hour = pd.Series({t: water(t) for t in T}).groupby(hours).sum()
    print("\nAgua por hora del día (¿produce de noche, cuando hace frío y es barato?):")
    print((100 * by_hour / by_hour.sum()).round(1).to_string())

    print("\nSector: nieve el 6 dic vs nieve mínima para abrir V")
    for p in m.P:
        print(f"  {p:4s} {snow_key[p]:>9,.0f}  /  {data['V'][p]:>7,.0f}"
              f"  {'abre' if snow_key[p] >= data['V'][p] else ''}")


if __name__ == "__main__":
    main()
