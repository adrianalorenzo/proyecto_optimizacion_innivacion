"""
plots.py  —  Persona A: figuras para el informe (PNG en results/figures/).

Lee los CSV que generan solve.py y los experimentos; no resuelve nada.

  fig_snow_heatmap      nieve en cada sector y día / nieve mínima V (s/V)
  fig_reservoir         agua en la balsa a lo largo del horizonte
  fig_water_by_hour     % del agua usada en cada bloque de 3 h del día
  fig_pareto            frontera beneficio (objetivo) frente a agua (S-A2)
  fig_flow              objetivo frente al caudal máximo Q_MAX (S-A2)
  fig_climate           objetivo en cada escenario climático (S-A1)
  fig_sensitivity       gráfico "tornado" de los supuestos físicos (S-A3)

Uso:  python src/plots.py                    (usa results/normal_operation)
      python src/plots.py --run calida_operation
"""

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402
import pandas as pd                      # noqa: E402
from matplotlib.colors import LinearSegmentedColormap   # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
EXP = RESULTS / "experiments"
FIG = RESULTS / "figures"

# Paleta (validada: azul y naranja pasan las comprobaciones de daltonismo)
SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
BLUE, ORANGE = "#2a78d6", "#eb6834"
SEQ = LinearSegmentedColormap.from_list(
    "azul", ["#f0efec", "#cde2fb", "#86b6ef", "#3987e5", "#1c5cab", "#0d366b"])

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "text.color": INK, "axes.titlecolor": INK, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "font.size": 10, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.spines.top": False, "axes.spines.right": False,
    "lines.linewidth": 2, "figure.dpi": 150,
})


def metric(t):
    """Columna a dibujar: el beneficio real (sin penalización) si existe; si no, el objetivo."""
    if "beneficio_real" in t.columns:
        return "beneficio_real", "beneficio (€, sin penalización)"
    return "objetivo", "valor del objetivo"


def save(fig, name):
    FIG.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(FIG / f"{name}.png", bbox_inches="tight")
    plt.close(fig)
    print(f"  {name}.png")


def fmt_thousands(ax, axis="y"):
    f = matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", "."))
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(f)


# ----------------------------------------------------------------------------
def snow_heatmap(run: Path, run_name: str):
    s = pd.read_csv(run / "s.csv")
    V = pd.read_csv(ROOT / "data" / "processed" / "pistas.csv").set_index("p")["V"]
    s["ratio"] = s["s"] / s["p"].map(V)
    order = sorted(s["p"].unique(), key=lambda p: int(p[1:]))
    mat = s.pivot(index="p", columns="d", values="ratio").loc[order]
    fig, ax = plt.subplots(figsize=(10, 4.6))
    im = ax.imshow(np.clip(mat.values, 0, 2), aspect="auto", cmap=SEQ, vmin=0, vmax=2)
    ax.set_yticks(range(len(order)), order)
    ticks = [0, 16, 21, 38, 47, 52]
    ax.set_xticks(ticks, ["15 nov", "1 dic", "6 dic", "23 dic", "1 ene", "6 ene"])
    ax.grid(False)
    cb = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
    cb.set_label("nieve / nieve mínima para abrir (s/V)", color=INK2)
    cb.outline.set_visible(False)
    ax.set_title(f"Nieve en pista por sector ({run_name}) — a partir de 1 se puede abrir")
    save(fig, f"fig_snow_heatmap_{run_name}")


def reservoir(run: Path, run_name: str):
    b = pd.read_csv(run / "b.csv")
    fig, ax = plt.subplots(figsize=(8, 3.4))
    ax.plot(b["d"], b["b"], color=BLUE)
    ax.set_xlabel("día del horizonte (0 = 15 nov)")
    ax.set_ylabel("m³ en la balsa")
    ax.set_ylim(0, None)
    fmt_thousands(ax)
    ax.set_title(f"Agua en la balsa ({run_name})")
    save(fig, f"fig_reservoir_{run_name}")


def water_by_hour(run: Path, run_name: str):
    import sys
    sys.path.insert(0, str(ROOT / "src"))
    from solve import load
    x = pd.read_csv(run / "x.csv")
    summary = pd.read_json(run / "summary.json", typ="series")
    data = load(summary["escenario"], quiet=True)
    x["agua"] = [data["PHI"][r.k] * data["G"][r.j, r.k, r.t] * r.x for r in x.itertuples()]
    hours = pd.read_csv(ROOT / "data" / "interim" / "periods.csv").set_index("t")["hour_start"]
    share = 100 * x.groupby(x["t"].map(hours))["agua"].sum() / x["agua"].sum()
    share = share.reindex(range(0, 24, 3), fill_value=0)
    fig, ax = plt.subplots(figsize=(7, 3.4))
    ax.bar([f"{h:02d}-{h + 3:02d} h" for h in share.index], share.values, color=BLUE, width=0.6)
    ax.axhline(12.5, color=MUTED, linewidth=1, linestyle="--")
    ax.set_ylabel("% del agua usada")
    ax.grid(axis="x", visible=False)
    ax.set_title(f"¿A qué hora se produce? ({run_name})")
    ax.set_xlabel("bloque de 3 h   (línea discontinua = reparto uniforme, 12,5 %)")
    save(fig, f"fig_water_by_hour_{run_name}")


def pareto():
    path = EXP / "water_pareto.csv"
    if not path.exists():
        return
    t = pd.read_csv(path).sort_values("agua_usada_m3")
    col, label = metric(t)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(t["agua_usada_m3"], t[col], color=BLUE, marker="o", markersize=6)
    for frac, w, val in zip(t["eps_frac"], t["agua_usada_m3"], t[col]):
        ax.annotate(f"{frac:.0%}", (w, val), textcoords="offset points",
                    xytext=(6, -12), fontsize=8, color=INK2)
    ax.set_xlabel("agua usada en el horizonte (m³)")
    ax.set_ylabel(label)
    fmt_thousands(ax)
    fmt_thousands(ax, "x")
    ax.set_title("Frontera de Pareto: beneficio frente a agua (ε = % del agua sin límite)")
    save(fig, "fig_pareto")


def flow():
    path = EXP / "water_flow.csv"
    if not path.exists():
        return
    t = pd.read_csv(path)
    col, label = metric(t)
    fig, ax = plt.subplots(figsize=(7, 3.6))
    ax.plot(t["factor_Q"] * 100, t[col], color=BLUE, marker="o", markersize=6)
    ax.set_xlabel("caudal de distribución (% del caso base: 1.250 m³ por bloque)")
    ax.set_ylabel(label)
    fmt_thousands(ax)
    conc = EXP / "water_concession.csv"
    if conc.exists():
        c = pd.read_csv(conc)
        cc, _ = metric(c)
        spread = 100 * abs(c[cc].max() / c[cc].min() - 1)
        msg = ("Recortar la concesión un 40 % o doblarla no cambia el objetivo"
               if spread < 0.5 else
               f"Recortar la concesión un 40 % o doblarla cambia el objetivo un {spread:.1f} %")
        ax.text(0.02, 0.95, msg, transform=ax.transAxes, color=INK2, fontsize=8, va="top")
    ax.set_title("Efecto del caudal de distribución")
    save(fig, "fig_flow")


def climate():
    for mode in ["operation", "investment"]:
        path = EXP / f"climate_{mode}.csv"
        if not path.exists():
            continue
        t = pd.read_csv(path)
        labels = {"fria": "Fría\n2020/21", "normal": "Normal\n2019/20", "calida": "Cálida\n2022/23",
                  "normal_plus1": "Normal\n+1 °C", "normal_plus2": "Normal\n+2 °C"}
        col, label = metric(t)
        fig, ax = plt.subplots(figsize=(7, 3.6))
        bars = ax.bar([labels.get(e, e) for e in t["escenario"]], t[col], color=BLUE, width=0.6)
        for b, v in zip(bars, t[col]):
            ax.text(b.get_x() + b.get_width() / 2, v, f"{v:,.0f}".replace(",", "."),
                    ha="center", va="bottom", fontsize=8, color=INK2)
        ax.set_ylabel(label)
        fmt_thousands(ax)
        ax.grid(axis="x", visible=False)
        ax.set_title(f"Escenarios climáticos ({mode})")
        save(fig, f"fig_climate_{mode}")


def sensitivity():
    path = EXP / "sensitivity_physics.csv"
    if not path.exists():
        return
    t = pd.read_csv(path)
    g = t.groupby("supuesto")
    lo = g.apply(lambda d: d.loc[d["valor"].idxmin()], include_groups=False)
    hi = g.apply(lambda d: d.loc[d["valor"].idxmax()], include_groups=False)
    span = (hi["var_obj_pct"] - lo["var_obj_pct"]).abs().sort_values()
    fig, ax = plt.subplots(figsize=(8, 3.8))
    y = np.arange(len(span))
    ax.barh(y, lo.loc[span.index, "var_obj_pct"], color=ORANGE, height=0.5, label="valor bajo")
    ax.barh(y, hi.loc[span.index, "var_obj_pct"], color=BLUE, height=0.5, label="valor alto")
    for i, s in enumerate(span.index):                  # etiqueta al final de cada barra
        for row in (lo.loc[s], hi.loc[s]):
            v = row["var_obj_pct"]
            ax.text(v + (0.4 if v >= 0 else -0.4), i, f"{row['valor']:g}", va="center",
                    ha="left" if v >= 0 else "right", fontsize=8, color=INK2)
    lim = max(abs(lo["var_obj_pct"]).max(), abs(hi["var_obj_pct"]).max()) + 3
    ax.set_xlim(-lim, lim)
    ax.set_yticks(y, span.index)
    ax.axvline(0, color=INK2, linewidth=1)
    ax.set_xlabel("cambio del objetivo respecto al caso base (%)")
    ax.grid(axis="y", visible=False)
    ax.legend(frameon=False, loc="lower right", fontsize=8)
    ax.set_title("¿Qué supuesto físico importa más?")
    save(fig, "fig_sensitivity")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default="normal_operation", help="carpeta dentro de results/")
    args = ap.parse_args()
    run = RESULTS / args.run
    print(f"Figuras en {FIG.relative_to(ROOT)}:")
    if run.exists():
        snow_heatmap(run, args.run)
        reservoir(run, args.run)
        water_by_hour(run, args.run)
    pareto()
    flow()
    climate()
    sensitivity()


if __name__ == "__main__":
    main()
