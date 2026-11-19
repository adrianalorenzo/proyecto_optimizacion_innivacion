"""
run_all.py  —  Reproduce TODOS los resultados del proyecto con un comando.

  python run_all.py                 todo (datos + modelo + experimentos + figuras)
  python run_all.py --skip-data     sin regenerar datos (usa data/processed tal cual)
  python run_all.py --only-plots    solo rehace las figuras

Orden:
  1. Datos (Persona A): weather -> process_weather -> snow_physics ->
     climate_scenarios -> water
  2. Datos (Persona B): economics, prices  (si existen)
  3. Casos base: normal en modo operación (x entera y continua) e inversión
  4. Experimentos: S-A1 climate_runs, S-A2 water_pareto, S-A3 sensitivity_physics,
     S-B1 budget_sweep, S-B2 aw_price_breakeven y clima en modo inversión
  5. Figuras (src/plots.py)

La descarga del clima (weather.py) solo baja lo que falta: los CSV de
data/raw/weather/ ya están en el repo, así que no hace falta internet.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
PY = sys.executable

DATA_A = ["weather.py", "process_weather.py", "snow_physics.py",
          "climate_scenarios.py", "water.py"]
DATA_B = ["economics.py", "prices.py"]
# Caso base de operación con x entera (resultado "oficial", Tabla de validación)
# y con x continua (para la comparación); inversión con x continua.
BASE_CASES = [["--scenario", "normal", "--mode", "operation", "--time-limit", "1200"],
              ["--scenario", "normal", "--mode", "operation", "--relax-x"],
              ["--scenario", "normal", "--mode", "investment", "--relax-x", "--time-limit", "1200"]]
EXPERIMENTS_A = [["climate_runs.py", "--mode", "operation", "--relax-x"],
                 ["water_pareto.py", "--scenario", "normal", "--relax-x"],
                 ["sensitivity_physics.py", "--scenario", "normal", "--relax-x"]]
EXPERIMENTS_B = [["climate_runs.py", "--mode", "investment", "--relax-x"],
                 ["budget_sweep.py", "--scenario", "normal", "--relax-x"],     # S-B1
                 ["aw_price_breakeven.py", "--relax-x"]]                      # S-B2


def run(script: Path, *args: str) -> None:
    if not script.exists():
        print(f"   (no existe {script.relative_to(ROOT)}, se salta)")
        return
    t = time.perf_counter()
    print(f"-> {script.relative_to(ROOT)} {' '.join(args)}")
    subprocess.run([PY, str(script), *args], cwd=ROOT, check=True)
    print(f"   ({time.perf_counter() - t:.0f} s)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-data", action="store_true")
    ap.add_argument("--only-plots", action="store_true")
    args = ap.parse_args()

    if not args.only_plots:
        if not args.skip_data:
            print("1. Datos")
            for s in DATA_A + DATA_B:
                run(SRC / s)
        print("2. Casos base")
        for a in BASE_CASES:
            run(SRC / "solve.py", *a)
        print("3. Experimentos")
        for e in EXPERIMENTS_A + EXPERIMENTS_B:
            run(SRC / "experiments" / e[0], *e[1:])
    print("4. Figuras")
    run(SRC / "plots.py")
    print("Hecho. Resultados en results/ y figuras en results/figures/")


if __name__ == "__main__":
    main()
