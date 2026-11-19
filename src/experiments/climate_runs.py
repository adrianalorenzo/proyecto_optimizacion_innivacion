"""
climate_runs.py  —  Persona A, análisis S-A1: escenarios climáticos.

Resuelve el modelo en los 5 escenarios (fria, normal, calida, normal_plus1,
normal_plus2) y junta los indicadores en una tabla: beneficio, ingresos, luz,
agua, días-sector abiertos, km incumplidos en días clave...

Con --mode investment hace lo mismo con inversión (útil para S-B2 de Adri:
¿con +2 °C compensa el all-weather?).

Guarda también los resultados completos de cada escenario en
results/<escenario>_<modo>/ (para las figuras de plots.py).

Salida: results/experiments/climate_<modo>.csv
Uso:    python src/experiments/climate_runs.py --mode operation
"""

import argparse

import pandas as pd

from common import save_table
from solve import solve_scenario

SCENARIOS = ["fria", "normal", "calida", "normal_plus1", "normal_plus2"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="operation", choices=["operation", "investment"])
    ap.add_argument("--solver", default=None)
    ap.add_argument("--gap", type=float, default=0.01)
    ap.add_argument("--time-limit", type=int, default=600)
    ap.add_argument("--relax-x", action="store_true", help="x continua (análisis largos)")
    args = ap.parse_args()

    rows = []
    for sc in SCENARIOS:
        summary, _, _ = solve_scenario(sc, args.mode, solver=args.solver, gap=args.gap,
                                       time_limit=args.time_limit, relax_x=args.relax_x, quiet=True)
        rows.append(summary)
        print(f"  {sc:13s} {summary['estado']:10s} obj={summary.get('objetivo')} "
              f"agua={summary.get('agua_usada_m3')} t={summary['t_resolucion_s']} s")
    table = pd.DataFrame(rows)
    path = save_table(table, f"climate_{args.mode}")
    print(f"Listo: {path}")


if __name__ == "__main__":
    main()
