"""
common.py  —  Utilidades compartidas por los experimentos.

- Añade src/ al path para poder importar model, solve, etc.
- Regenera en memoria (sin tocar los ficheros) los datos de un escenario
  cuando un experimento cambia un supuesto físico: producción G/A/E y
  pérdidas DELTA / nieve natural Z.
- Guarda tablas de resultados en results/experiments/.
"""

import contextlib
import io
import sys
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parents[1]
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import process_weather as pw          # noqa: E402
import snow_physics as sp             # noqa: E402
from solve import ROOT, load, solve_scenario   # noqa: E402,F401

OUT = ROOT / "results" / "experiments"


def scenario_definition(scenario: str) -> tuple[int, float]:
    """(temporada base, calentamiento dT) de un escenario."""
    if scenario[:4].isdigit():                       # "2019_2020"
        return int(scenario[:4]), 0.0
    tab = pd.read_csv(pw.SCEN_DIR / "scenarios.csv").set_index("escenario")
    return int(str(tab.loc[scenario, "temporada_base"])[:4]), float(tab.loc[scenario, "dT"])


def raw_hours(scenario: str, extra_dT: float = 0.0) -> pd.DataFrame:
    """Datos horarios del escenario (con su calentamiento + extra_dT si lo hay)."""
    import climate_scenarios as cs
    season, dT = scenario_definition(scenario)
    if dT + extra_dT:
        return cs.warmed_season(season, dT + extra_dT)
    return pd.read_csv(pw.RAW_DIR / f"weather_{season}_{season + 1}.csv",
                       parse_dates=["datetime"])


def regen_production(data: dict, scenario: str, extra_dT: float = 0.0) -> dict:
    """Recalcula G, A, E con los parámetros ACTUALES de process_weather /
    snowmaking (los experimentos los cambian antes de llamar)."""
    with contextlib.redirect_stdout(io.StringIO()):
        pos = pw.load_positions()
        wind_thr = pw.wind_threshold_all_seasons()
    hours = pw.add_time_indices(raw_hours(scenario, extra_dT))
    b = pw.to_blocks(pw.hourly_by_position(hours, pos, wind_thr))
    G, A, E = {}, {}, {}
    for r in b.itertuples():
        for k in ("FAN", "AW"):
            G[r.j, k, r.t] = getattr(r, f"G_{k}")
            A[r.j, k, r.t] = getattr(r, f"A_{k}")
            E[r.j, k, r.t] = getattr(r, f"E_{k}")
    return dict(data, G=G, A=A, E=E)


def regen_snow(data: dict, scenario: str) -> dict:
    """Recalcula DELTA y Z con los parámetros ACTUALES de snow_physics."""
    with contextlib.redirect_stdout(io.StringIO()):
        snow = sp.snow_for_season(raw_hours(scenario), sp.sector_altitudes(), sp.sector_areas())
    snow["Z"] = snow["Z"].fillna(0.0)
    return dict(data,
                DELTA={(r.p, r.d): r.Delta for r in snow.itertuples()},
                Z={(r.p, r.d): r.Z for r in snow.itertuples()})


def save_table(df: pd.DataFrame, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.csv"
    df.to_csv(path, index=False)
    return path


def quiet_load(scenario: str) -> dict:
    with contextlib.redirect_stdout(io.StringIO()):
        return load(scenario)
