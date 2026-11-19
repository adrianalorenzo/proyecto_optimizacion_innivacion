"""
Qué hace
--------
Descarga de Open-Meteo (API histórica, reanálisis ERA5) la temperatura, la
humedad relativa, el viento y la nieve caída, hora a hora, en Sierra Nevada,
para el horizonte del modelo (15 nov – 6 ene) de las temporadas 2015/16 a 2024/25.
Guarda un CSV por temporada en data/raw/weather/.

Decisiones
----------
- Un único punto de referencia (Pradollano, 37.09 N, -3.40 E) a una COTA DE
  REFERENCIA de 2500 m. Open-Meteo corrige la temperatura a la cota que le
  pidamos. Después (process_weather.py) se pasa de esta cota a la de cada
  posición j con el gradiente de -0,65 °C / 100 m.
- ERA5 tiene una resolución de unos 25 km: no distingue unas pistas de otras.
  Por eso las diferencias entre posiciones salen solo de la cota (gradiente)
  y del factor de exposición al viento (supuesto).
- Hora local (Europe/Madrid), porque el precio de la electricidad y los
  bloques de 3 h van en hora local.
"""

from pathlib import Path
import time

import pandas as pd
import requests

# ----------------------------------------------------------------------------
# Configuración
# ----------------------------------------------------------------------------
URL = "https://archive-api.open-meteo.com/v1/archive"

LAT, LON = 37.09, -3.40          # Pradollano, Sierra Nevada
REF_ELEVATION_M = 2500           # cota de referencia (m); luego gradiente a cada j

HOURLY_VARS = [
    "temperature_2m",            # °C   -> temperatura seca
    "relative_humidity_2m",      # %    -> para el bulbo húmedo (Stull)
    "wind_speed_10m",            # km/h -> viento medio
    "wind_gusts_10m",            # km/h -> rachas (umbral ~30 km/h para FAN)
    "snowfall",                  # cm   -> nieve natural (para Z_{p,d})
]

FIRST_SEASON, LAST_SEASON = 2015, 2024   # temporada 2015 = 15/11/2015 – 06/01/2016

OUT_DIR = Path(__file__).resolve().parents[1] / "data" / "raw" / "weather"


# ----------------------------------------------------------------------------
# Funciones
# ----------------------------------------------------------------------------
def download_season(season: int) -> pd.DataFrame:
    """Descarga los datos horarios del 15 nov de `season` al 6 ene de `season+1`."""
    params = {
        "latitude": LAT,
        "longitude": LON,
        "elevation": REF_ELEVATION_M,
        "start_date": f"{season}-11-15",
        "end_date": f"{season + 1}-01-06",
        "hourly": ",".join(HOURLY_VARS),
        "timezone": "Europe/Madrid",
        "wind_speed_unit": "kmh",
    }
    r = requests.get(URL, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()["hourly"]

    df = pd.DataFrame(data).rename(columns={"time": "datetime"})
    df["datetime"] = pd.to_datetime(df["datetime"])
    df.insert(0, "season", season)
    return df


def check_season(df: pd.DataFrame, season: int) -> None:
    """Comprobaciones básicas: nº de horas esperado y huecos."""
    expected_hours = 53 * 24     # 15 nov – 6 ene = 53 días
    n_missing = int(df[HOURLY_VARS].isna().sum().sum())
    print(f"  temporada {season}/{season + 1}: {len(df)} horas "
          f"(esperadas {expected_hours}), valores vacíos: {n_missing}, "
          f"T media {df['temperature_2m'].mean():.1f} °C")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for season in range(FIRST_SEASON, LAST_SEASON + 1):
        out = OUT_DIR / f"weather_{season}_{season + 1}.csv"
        if out.exists():
            print(f"  {out.name} ya existe, se salta")
            continue
        df = download_season(season)
        check_season(df, season)
        df.to_csv(out, index=False)
        time.sleep(1)            # para no saturar la API gratuita
    print(f"Listo. CSV en {OUT_DIR}")


if __name__ == "__main__":
    main()
