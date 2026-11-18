"""
Hacemos el análisis de sensibilidad para ver cuánto nos compensa invertir.
Este script consiste en cambiar el presupuesto muchas veces para ver cómo difiere el resultado

"""

import argparse
from pathlib import Path

import pandas as pd

from common import OUT                    #common.py ya deja importar los módulos de src/
from solve import ROOT, kpis, load, prepare, restrict_days, run_solver


FIG = ROOT/ "results" / "figures"
BUDGETS = [0,250_000,500_000, 1_000_000, 2_000_000, 3_000_000, 5_000_000, 8_000_000]

def solve_case(data, mode, args, label):
    m = prepare(data, mode, quiet=True)
    status, gap, secs, _ = run_solver(m, args.solver, args.gap, args.time_limit, quiet=True)
    row = {"caso": label, "modo":mode, "estado": status,
           "gap": None if gap is None else round(gap, 4), "t_s": round(secs, 1)}
    if status != "sin_solucion":
        row.update(kpis(m, data))
    print(f" {label:16s} {status:12s} beneficio={row.get('objetivo')} " 
          f"inversion={row.get('investment')} equipos={row.get('equipos_nuevos')}")
    return row, m 

def installed(m, data, psi):
    """Qué se instala en cada posición candidata habilitada"""
    rows = []
    for j in m.JN:
        if round(m.u[j].value or 0)==1:
            p=next(p for p, js in data["Jp"].items() if j in js)
            n= {k: round(m.n[j, k].value or 0) for k in m.K}
            cost = data["F"][j] + sum(data["C"][k] * n[k] for k in m.K)
            rows.append({"PSI": psi, "j": j, "p":p, "n_FAN": n["FAN"], "n_AW": n["AW"],
                         "coste_total_eur": cost})
    return rows

def plot(table: pd.DataFrame, base_obj: float) -> Path:
    import matplotlib.pyplot as plt
    FIG.mkdir(parents=True, exist_ok=True)
    t = table[table["modo"] == "investment"]
    fig, ax = plt.subplots(figsize=(7,4))
    ax.plot(t["PSI"]/ 1e6, t["objetivo"] /1e3, marker="o", label="(b) inversión + operación")
    ax.axhline(base_obj/1e3, color="grey", ls="--", label="(a) solo operación")
    ax.set_xlabel("Presupuesto de inversión (millones de euros)")
    ax.set_ylabel("Beneficio en el horizonte (miles de euros)")
    ax.set_title("S-B1: beneficio frente a presupuesto")
    ax.legend()
    path = FIG/ "budget_sweep.png"
    fig.savefig(path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    return path

def main()-> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="normal")
    ap.add_argument("--solver", default=None)
    ap.add_argument("--gap", type=float, default=0.01)
    ap.add_argument("--time-limit", type=int, default=600)
    ap.add_argument("--days", type=int, default=None, help="recortar el horizonte (pruebas)")
    args = ap.parse_args()

    base = load(args.scenario, quiet=True)
    if args.days:
        base = restrict_days(base, args.days)

    print("Modo (a): solo operación")
    row_a, _ = solve_case(base, "operation", args, "operación (a)")
    rows, detail = [dict(row_a, PSI=None)], []

    print("Modo (b): inversión + operación, barrido de PSI")
    for psi in BUDGETS:
        row, m = solve_case(dict(base, PSI=psi), "investment", args, f"PSI = {psi / 1e6:.2f} M€")
        rows.append(dict(row, PSI=psi))
        OUT.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(OUT / "budget_sweep.csv", index=False)   # guarda lo que lleva
        if row["estado"] != "sin_solucion":
            detail += installed(m, base, psi)

    table = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT / "budget_sweep.csv", index=False)
    pd.DataFrame(detail).to_csv(OUT / "budget_sweep_detalle.csv", index=False)

    #Cordura: con PSI = 0, (b) = (a)
    b0 = table.loc[table["PSI"] == 0, "objetivo"].iloc[0]
    print(f"Comprobación PSI = 0: (a) = {row_a['objetivo']:,.0f} €  |  (b) = {b0:,.0f} €")
    print(f"Figura: {plot(table, row_a['objetivo'])}")
    print(f"Tablas en {OUT}")


if __name__ == "__main__":
    main()