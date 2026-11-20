"""
Análisis S-B3: sensibilidad a los supuestos económicos

Resolvemos el modo inversión (presupuesto base) cambiando de uno en uno los parámetros económicos más inciertos, y comparamos con el caso base:
-precio de la electricidad + 30%
-theta (fracción de la anualidad imputada al horizonte): 0.15 y 0.35 (base 0.23)
-penalización por km incumplido M_KM: 0 y 15000 euros/km (como base: 5000)
"""

import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


#reutilizamos lo que podemos de cada fichero
from common import OUT
from load_data import PROC, crf, read_yaml_simple
from solve import ROOT, kpis, load, prepare, restrict_days, run_solver

FIG = ROOT / "results" / "figures"

def change_electricity(data, factor):
    #copiamos los datos con la luz más cara
    #multplicamos cada precio por un factor
    PI = {t: price*factor for t, price in data["PI"].items()}
    return dict(data, PI=PI)

def change_annual_costs(data, theta, r):
    """Recalcula los costes imputados al horizonte según va variando theta"""
    
    eco = read_yaml_simple(PROC/ "economics.yaml")
    tech = pd.read_csv(PROC/ "tech.csv").set_index("k")
    #recalculamos el coste para habilitar cada posicon
    FA = {j: F*crf(r, eco["life_positions"])*theta for j,F in data["F"].items()}
    #y para cada equipo
    CA = {k: data["C"][k]*crf(r, tech.loc[k, "life_years"])*theta for k in data["K"]}
    return dict(data, FA=FA, CA=CA) #nueva copia de los datos


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="normal")
    ap.add_argument("--solver", default=None)
    ap.add_argument("--gap", type=float, default=0.01)
    ap.add_argument("--time-limit", type=int, default=600)
    ap.add_argument("--days", type=int, default=None, help="recortar el horizonte (pruebas)")
    ap.add_argument("--relax-x", action="store_true", help="x continua (más rápido)")
    args = ap.parse_args()

    base = load(args.scenario, quiet=True)
    if args.days:
        base = restrict_days(base, args.days)
    eco = read_yaml_simple(PROC / "economics.yaml")
    r = eco["r"]

    cases = [
        ("Caso base", base),
        ("Electricidad +30 %", change_electricity(base, 1.3)),
        ("theta = 0,15", change_annual_costs(base, 0.15, r)),
        ("theta = 0,35", change_annual_costs(base, 0.35, r)),
        ("M_KM = 0", dict(base, M_KM=0.0)),
        ("M_KM = 15.000", dict(base, M_KM=15000.0)),
    ]

    rows = []
    for name, data in cases:
        m = prepare(data, "investment", relax_x=args.relax_x, quiet=True)
        status, gap, secs, _ = run_solver(m, args.solver, args.gap, args.time_limit, quiet=True)
        row = {"caso": name, "estado": status, "gap": gap, "t_s": round(secs, 1)}
        if status != "sin_solucion":
            row.update(kpis(m, data))
        rows.append(row)
        OUT.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(OUT / "economic_sensitivity.csv", index=False)   # guarda lo que lleva
        print(f" {name:20s} {status:12s} beneficio_real = {row.get('beneficio_real')}  "
              f"km_incumplidos = {row.get('km_incumplidos_total')}  equipos = {row.get('equipos_nuevos')}")

    # Figura: variación del beneficio real respecto al caso base
    table = pd.DataFrame(rows)
    b0 = table.loc[0, "beneficio_real"]
    table["var_beneficio_pct"] = 100 * (table["beneficio_real"] - b0) / b0
    table.to_csv(OUT / "economic_sensitivity.csv", index=False)

    t = table.iloc[1:]
    FIG.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.barh(t["caso"], t["var_beneficio_pct"])
    ax.axvline(0, color="grey")
    ax.set_xlabel("Variación del beneficio real respecto al caso base (%)")
    ax.set_title("S-B3: sensibilidad a los supuestos económicos")
    fig.savefig(FIG / "economic_sensitivity.png", bbox_inches="tight", dpi=150)
    plt.close(fig)
    print(f"Tabla en {OUT / 'economic_sensitivity.csv'} y figura en {FIG / 'economic_sensitivity.png'}")


if __name__ == "__main__":
    main()