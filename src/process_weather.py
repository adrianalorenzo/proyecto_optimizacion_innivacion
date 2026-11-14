"""
process_weather.py  —  Persona A, tareas A2 y A3.

De los datos horarios de Open-Meteo (cota de referencia 2500 m) a datos por
posición j y bloque de 3 h t, que es la resolución temporal del modelo.

Pasos
-----
1. Temperatura en cada posición:  T_j = T_ref - 0,65 °C/100 m * (cota_j - 2500)
2. Bulbo húmedo (Stull, 2011) con T_j y la humedad relativa.
3. Hora ventosa (umbral RELATIVO): el viento en la posición es el viento de
   referencia × factor de exposición (columna exposure de positions.csv,
   1,0 = resguardada ... 1,3 = muy expuesta). La hora es ventosa si ese viento
   supera el percentil WIND_PERCENTILE del viento de referencia de las 10
   temporadas juntas. Con exposición 1,0 se pierde el 15 % de las horas; con
   exposición mayor, más.
4. Hora apta:  FAN -> Tw_j <= -2 °C y no ventosa
               AW  -> siempre (SnowFactory: produce sea cual sea la temperatura
                      del aire y está dentro de un contenedor, sin viento)
5. Bloques de 3 h: A_{j,k,t} = 1 si al menos MIN_APT_HOURS de las 3 horas son
   aptas.
6. Producción y energía por equipo y bloque (curvas de src/snowmaking.py):
   G_{j,k,t} = suma de la producción de las horas aptas del bloque (0 si A = 0)
   E_{j,k,t} = KWH_PER_M3[k] * G_{j,k,t}

Salidas (data/interim/, ficheros intermedios para la tarea A3)
---------------------------------------------------------------
- periods.csv         t, d, block, date (MM-DD), hour_start      (común a todas las temporadas)
- weather_blocks.csv  season, j, t, T, Tw, Tw_min, n_apt_FAN, n_apt_AW, A_FAN, A_AW
- snowfall_days.csv   season, d, snowfall_cm   (nieve natural a la cota de referencia)

Salida para el modelo (data/processed/scenarios/<temporada>/)
-------------------------------------------------------------
- production.csv      j, k, t, A, G, E     (formato de la sección 5 del plan)

Supuestos a explicar en el informe
----------------------------------
- Gradiente vertical constante de -0,65 °C/100 m (atmósfera estándar). En
  inversiones térmicas (frecuentes de noche en invierno) es falso.
- La humedad relativa no cambia con la cota.
- Fórmula de Stull calibrada a presión del nivel del mar; a 2500 m el error es
  pequeño frente a la incertidumbre del reanálisis.
- Viento: ERA5 subestima el viento en montaña y las rachas son incoherentes
  entre temporadas, por eso se usa un umbral relativo sobre el viento medio
  (percentiles = parámetro de sensibilidad, tarea S-A3).

Uso:  python src/process_weather.py            (desde la raíz del repo)
"""

from pathlib import Path

import numpy as np
import pandas as pd

from snowmaking import AW_M3_PER_HOUR, KWH_PER_M3, TECHS, fan_production_m3h

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "weather"
OUT_DIR = ROOT / "data" / "interim"
SCEN_DIR = ROOT / "data" / "processed" / "scenarios"

# Fichero de posiciones: el de Adri cuando exista; si no, el provisional.
POSITIONS_FILE = ROOT / "data" / "processed" / "positions.csv"
POSITIONS_PROVISIONAL = ROOT / "data" / "interim" / "positions_provisional.csv"

# ----------------------------------------------------------------------------
# Parámetros (todos son supuestos documentados -> candidatos a sensibilidad)
# ----------------------------------------------------------------------------
REF_ELEVATION_M = 2500
LAPSE_RATE = -0.65 / 100          # °C por metro
TW_MAX_FAN = -2.0                 # bulbo húmedo máximo para el ventilador (°C)
WIND_PERCENTILE = 0.85            # umbral = percentil 85 del viento de referencia
HOURS_PER_BLOCK = 3
MIN_APT_HOURS = 2                 # horas aptas (de 3) para que el bloque cuente como apto


# ----------------------------------------------------------------------------
def stull_wet_bulb(T: pd.Series, RH: pd.Series) -> pd.Series:
    """Temperatura de bulbo húmedo (°C) con la fórmula empírica de Stull (2011).
    Válida para RH entre 5 % y 99 % y T entre -20 °C y 50 °C."""
    RH = RH.clip(5, 99)
    return (T * np.arctan(0.151977 * np.sqrt(RH + 8.313659))
            + np.arctan(T + RH) - np.arctan(RH - 1.676331)
            + 0.00391838 * RH ** 1.5 * np.arctan(0.023101 * RH)
            - 4.686035)


def load_raw() -> pd.DataFrame:
    """Une las 10 temporadas y añade los índices de día d y bloque t."""
    df = pd.concat([pd.read_csv(f, parse_dates=["datetime"])
                    for f in sorted(RAW_DIR.glob("weather_*.csv"))],
                   ignore_index=True)
    start = pd.to_datetime(df["season"].astype(str) + "-11-15")
    hour_idx = ((df["datetime"] - start).dt.total_seconds() // 3600).astype(int)
    df["d"] = hour_idx // 24                       # 0..52
    df["block"] = df["datetime"].dt.hour // HOURS_PER_BLOCK   # 0..7
    df["t"] = df["d"] * (24 // HOURS_PER_BLOCK) + df["block"]  # 0..423
    return df


def load_positions() -> pd.DataFrame:
    path = POSITIONS_FILE if POSITIONS_FILE.exists() else POSITIONS_PROVISIONAL
    print(f"Posiciones leídas de: {path.relative_to(ROOT)}")
    pos = pd.read_csv(path)
    return pos[["j", "altitude_m", "exposure"]].astype({"exposure": float})


def hourly_by_position(df: pd.DataFrame, pos: pd.DataFrame) -> pd.DataFrame:
    """Para cada posición y hora: T, Tw, hora ventosa y aptitud por tecnología."""
    out = []
    for _, row in pos.iterrows():
        h = df[["season", "d", "block", "t", "datetime", "relative_humidity_2m",
                "wind_speed_10m"]].copy()
        h["j"] = row["j"]
        h["T"] = df["temperature_2m"] + LAPSE_RATE * (row["altitude_m"] - REF_ELEVATION_M)
        h["Tw"] = stull_wet_bulb(h["T"], h["relative_humidity_2m"])

        # Umbral relativo: un único umbral para las 10 temporadas juntas
        wind_threshold = df["wind_speed_10m"].quantile(WIND_PERCENTILE)
        h["windy"] = h["wind_speed_10m"] * row["exposure"] > wind_threshold

        h["apt_FAN"] = (h["Tw"] <= TW_MAX_FAN) & ~h["windy"]
        h["apt_AW"] = True

        # Producción horaria de UN equipo (m³), solo en horas aptas
        h["g_FAN"] = fan_production_m3h(h["Tw"]) * h["apt_FAN"]
        h["g_AW"] = AW_M3_PER_HOUR * h["apt_AW"]
        out.append(h)
    return pd.concat(out, ignore_index=True)


def to_blocks(h: pd.DataFrame) -> pd.DataFrame:
    """Agrega las horas en bloques de 3 h."""
    b = (h.groupby(["season", "j", "t"])
           .agg(T=("T", "mean"), Tw=("Tw", "mean"), Tw_min=("Tw", "min"),
                n_apt_FAN=("apt_FAN", "sum"), n_apt_AW=("apt_AW", "sum"),
                G_FAN=("g_FAN", "sum"), G_AW=("g_AW", "sum"))
           .reset_index())
    for k in TECHS:
        b[f"A_{k}"] = (b[f"n_apt_{k}"] >= MIN_APT_HOURS).astype(int)
        b[f"G_{k}"] = b[f"G_{k}"] * b[f"A_{k}"]          # bloque no apto -> no produce
        b[f"E_{k}"] = KWH_PER_M3[k] * b[f"G_{k}"]
    return b.round(2)


def write_production(blocks: pd.DataFrame) -> None:
    """production.csv (j, k, t, A, G, E) para cada temporada = escenario."""
    for season, b in blocks.groupby("season"):
        rows = [b[["j", "t", f"A_{k}", f"G_{k}", f"E_{k}"]]
                .rename(columns={f"A_{k}": "A", f"G_{k}": "G", f"E_{k}": "E"})
                .assign(k=k) for k in TECHS]
        prod = pd.concat(rows)[["j", "k", "t", "A", "G", "E"]].sort_values(["j", "k", "t"])
        out = SCEN_DIR / f"{season}_{season + 1}"
        out.mkdir(parents=True, exist_ok=True)
        prod.to_csv(out / "production.csv", index=False)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = load_raw()
    pos = load_positions()

    # periods.csv: igual para todas las temporadas
    periods = (df[df["season"] == df["season"].min()]
               .groupby("t").agg(d=("d", "first"), block=("block", "first"),
                                 datetime=("datetime", "first"))
               .reset_index())
    periods["date"] = periods["datetime"].dt.strftime("%m-%d")
    periods["hour_start"] = periods["block"] * HOURS_PER_BLOCK
    periods[["t", "d", "block", "date", "hour_start"]].to_csv(OUT_DIR / "periods.csv", index=False)

    blocks = to_blocks(hourly_by_position(df, pos))
    blocks.to_csv(OUT_DIR / "weather_blocks.csv", index=False)
    write_production(blocks)

    snow = df.groupby(["season", "d"])["snowfall"].sum().rename("snowfall_cm").reset_index()
    snow.to_csv(OUT_DIR / "snowfall_days.csv", index=False)

    # Resumen para comprobar que tiene sentido
    summary = blocks.groupby("season").agg(
        pct_aptos_FAN=("A_FAN", lambda x: round(100 * x.mean(), 1)),
        nieve_FAN_m3=("G_FAN", lambda x: round(x.sum() / blocks["j"].nunique())),
        nieve_AW_m3=("G_AW", lambda x: round(x.sum() / blocks["j"].nunique())))
    print("Por equipo y temporada (media de las posiciones):")
    print(summary.to_string())
    print(f"Listo. Ficheros en {OUT_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
