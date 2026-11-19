"""
water_pareto.py  —  Análisis del agua.

Tres preguntas:
1. CONCESIÓN: ¿qué pasa si la CHG reduce la concesión (-20 %, -40 %) o si
   hubiera aceptado la ampliación que pidió Cetursa (725.749 m³/año, BOE
   2023)?  -> cambia W.
2. CAUDAL: ¿y si se amplía la capacidad de bombeo/caudal (Q_MAX)? Sirve para
   ver qué recurso limita de verdad: la concesión (agua total) o el caudal
   (agua por bloque de 3 h).
3. FRONTERA DE PARETO (ε-restricción): segundo objetivo = gastar menos agua.
   Se resuelve sin límite extra, se mide el agua usada w*, y se vuelve a
   resolver con R6: agua <= ε para ε = 100 %, 90 %, ..., 30 % de w*.
   Cada punto dice cuánto beneficio se pierde por ahorrar ese agua.

Salidas (results/experiments/): water_concession.csv, water_flow.csv,
water_pareto.csv

Uso:  python src/experiments/water_pareto.py --scenario normal
"""

import argparse

import pandas as pd

from common import quiet_load, save_table
from solve import kpis, prepare, run_solver

ANNUAL_CONCESSION = 350_000
REQUESTED_CONCESSION = 725_749          # BOE-B-2023-35624
CONCESSION_CASES = {"-40 %": 0.6, "-20 %": 0.8, "actual": 1.0,
                    "ampliación pedida": REQUESTED_CONCESSION / ANNUAL_CONCESSION}
FLOW_CASES = [0.5, 0.75, 1.0, 1.5]     # x Q_MAX base (0,5 = el antiguo dato de CCOO)
EPS_FRACTIONS = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3]


def solve_case(data, args, mode="operation", label=None):
    m = prepare(data, mode, relax_x=args.relax_x, quiet=True)
    status, gap, secs, _ = run_solver(m, args.solver, args.gap, args.time_limit, quiet=True)
    row = {"caso": label, "estado": status, "gap": gap, "t_s": round(secs, 1)}
    if status != "sin_solucion":
        row.update(kpis(m, data))
    print(f"  {label:22s} {status:12s} obj={row.get('objetivo')}  agua={row.get('agua_usada_m3')}")
    return row, m


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="normal")
    ap.add_argument("--solver", default=None)
    ap.add_argument("--gap", type=float, default=0.01)
    ap.add_argument("--time-limit", type=int, default=300)
    ap.add_argument("--relax-x", action="store_true", help="x continua (análisis largos)")
    args = ap.parse_args()
    base = quiet_load(args.scenario)

    print("1) Concesión")
    rows = []
    for label, f in CONCESSION_CASES.items():
        row, _ = solve_case(dict(base, W=base["W"] * f), args, label=label)
        rows.append({"concesion_anual_m3": round(ANNUAL_CONCESSION * f), "W_m3": base["W"] * f, **row})
    save_table(pd.DataFrame(rows), "water_concession")

    print("2) Caudal máximo por bloque")
    rows = []
    for f in FLOW_CASES:
        row, _ = solve_case(dict(base, Q_MAX=base["Q_MAX"] * f), args, label=f"Q_MAX x{f}")
        rows.append({"factor_Q": f, "Q_MAX_m3_bloque": base["Q_MAX"] * f, **row})
    save_table(pd.DataFrame(rows), "water_flow")

    print("3) Frontera de Pareto (ε-restricción sobre el agua)")
    first, m = solve_case(base, args, label="sin límite extra")
    w_star = first["agua_usada_m3"]
    rows = []
    for frac in EPS_FRACTIONS:
        m.W_EPS = min(frac * w_star, base["W"])          # mismo modelo, nuevo ε
        status, gap, secs, _ = run_solver(m, args.solver, args.gap, args.time_limit, quiet=True)
        row = {"eps_frac": frac, "eps_m3": frac * w_star, "estado": status, "gap": gap}
        if status != "sin_solucion":
            row.update(kpis(m, base))
        rows.append(row)
        print(f"  ε = {frac:.0%} de w*  obj={row.get('objetivo')}  agua={row.get('agua_usada_m3')}")
    path = save_table(pd.DataFrame(rows), "water_pareto")
    print(f"Listo. Tablas en {path.parent}")


if __name__ == "__main__":
    main()
