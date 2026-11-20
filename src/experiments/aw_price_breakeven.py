"""
Análisis S-B2: vamos a ver a qué precio compensaría all-weather (AW)

Para cada escenario climático (normal, 1º, 2º) resolvemos el modo inversión, 
bajando el precio del AW y miramos a partir de qué precio el modelo decide comprar alguno.
Así, podemos ver el precio máximo que tendría sentido pagar y cómo cambia con el calentamiento

"""
import argparse
import pandas as pd

from common import OUT
from solve import ROOT, kpis, load, prepare, restrict_days, run_solver

FIG = ROOT / "results" / "figures"
NAMES = {"normal": "Normal", "normal_plus1": "+1 °C", "normal_plus2": "+2 °C"}

SCENARIOS = ["normal", "normal_plus1", "normal_plus2"]
PRICES = [1_000_000, 600_000, 400_000, 250_000, 100_000, 50_000, 0]    #euros por equipo AW (0 = gratis)

def with_aw_price(data, price):
    """Copia de los datos con otro precio del AW (coste total y coste imputado al horizonte)"""
    factor = price/data["C"]["AW"]
    C = dict(data["C"])
    CA = dict(data["CA"])
    C["AW"] = price
    CA["AW"] = data["CA"]["AW"]*factor #el coste imputado es proporcional al precio
    return dict(data, C=C, CA=CA)


def plot(table):
    """AW comprados y beneficio real frente al precio del AW, una línea por escenario"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    FIG.mkdir(parents=True, exist_ok=True)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    for scenario, t in table.groupby("escenario"):
        t = t.sort_values("precio_AW")
        label = NAMES.get(scenario, scenario)
        ax1.plot(t["precio_AW"] / 1e3, t["n_AW"], marker="o", label=label)
        ax2.plot(t["precio_AW"] / 1e3, t["beneficio_real"] / 1e6, marker="o", label=label)
    ax1.set_xlabel("Precio del all-weather (miles de euros)")
    ax1.set_ylabel("Equipos all-weather comprados")
    ax2.set_xlabel("Precio del all-weather (miles de euros)")
    ax2.set_ylabel("Beneficio real (millones de euros)")
    ax1.legend()
    fig.suptitle("S-B2: precio del all-weather")
    path = FIG / "aw_price_breakeven.png"
    fig.savefig(path, bbox_inches="tight", dpi=150)
    plt.close(fig)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenarios", nargs="+", default=SCENARIOS)
    ap.add_argument("--solver", default=None)
    ap.add_argument("--gap", type=float, default=0.01)
    ap.add_argument("--time-limit", type=int, default=600)
    ap.add_argument("--days", type=int, default=None, help="recortar el horizonte (pruebas)")
    ap.add_argument("--relax-x", action="store_true", help="x continua (más rápido)")
    ap.add_argument("--plot-only", action="store_true", help="solo rehace la figura con el CSV guardado")
    args = ap.parse_args()

    if args.plot_only:
        table = pd.read_csv(OUT / "aw_price_breakeven.csv")
        if "normal" not in set(table["escenario"]):        # la normal se ejecutó aparte
            normal = pd.read_csv(OUT / "aw_price_breakeven_normal.csv").query("escenario == 'normal'")
            table = pd.concat([normal, table])
        print(f"Figura: {plot(table)}")
        return

    rows = []
    for scenario in args.scenarios:
        base = load(scenario, quiet=True)
        if args.days:
            base = restrict_days(base, args.days)

        for price in PRICES:
            data = with_aw_price(base, price)
            m = prepare(data, "investment", relax_x=args.relax_x, quiet=True)
            status, gap, secs, _ = run_solver(m, args.solver, args.gap, args.time_limit, quiet=True)
            row = {"escenario": scenario, "precio_AW": price, "estado": status, "gap": gap,
                   "t_s": round(secs, 1)}
            if status != "sin_solucion":
                row.update(kpis(m, data))
                row["n_AW"] = row["equipos_nuevos"]["AW"]
                row["n_FAN"] = row["equipos_nuevos"]["FAN"]
            rows.append(row)
            OUT.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(rows).to_csv(OUT / "aw_price_breakeven.csv", index=False)   #guarda lo que lleva hecho
            print(f" {scenario:13s} precio AW = {price:>9,} €  {status:10s} "
                  f"AW nuevos = {row.get('n_AW')}  beneficio_real = {row.get('beneficio_real')}")

    table = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    table.to_csv(OUT / "aw_price_breakeven.csv", index=False)

    # Precio máximo al que compra al menos un AW, en cada escenario
    print("\nPrecio máximo al que compensa comprar AW:")
    for scenario in args.scenarios:
        t = table[(table["escenario"] == scenario) & (table["n_AW"] > 0)]
        if len(t) == 0:
            print(f"  {scenario:13s} no compra AW ni a {min(PRICES):,} €")
        else:
            print(f"  {scenario:13s} {t['precio_AW'].max():,} €")
    print(f"Tabla en {OUT / 'aw_price_breakeven.csv'}")
    print(f"Figura: {plot(table)}")


if __name__ == "__main__":
    main()
