"""
snow_physics.py  —  Persona A, tarea A4: pérdidas de nieve, nieve natural y nieve inicial.

Calcula, para cada temporada (escenario), sector p y día d:
    DELTA_{p,d}  tasa de pérdida diaria (fracción de la nieve que se pierde)
    Z_{p,d}      nieve natural caída, en m³ de nieve pisada equivalente
y la nieve inicial S0_p.

1) Pérdidas: modelo grado-día + evaposublimación
------------------------------------------------
Pérdida diaria en mm de agua equivalente (w.e.):
    melt_{p,d} = DDF * PDD_{p,d}            PDD = max(T media diaria - 0 °C, 0)
    loss_{p,d} = melt_{p,d} + SUBL
Se usa la temperatura MEDIA DIARIA porque los factores grado-día de la
literatura están calibrados así (con la suma horaria de grados positivos
saldría algo más de fusión con un DDF que no le corresponde).

En la restricción R2 la pérdida es PROPORCIONAL a la nieve acumulada
(s_{p,d} = (1 - DELTA_{p,d}) s_{p,d-1} + ...), así que la pasamos a fracción
dividiendo entre el agua equivalente de un manto de referencia:
    DELTA_{p,d} = loss_{p,d} / SWE_REF,   SWE_REF = H_REF * densidad
Por qué proporcional y no absoluta: es lineal y SIEMPRE factible (una pérdida
absoluta fija podría pedir más nieve de la que hay y hacer el modelo
infactible). Precio: sobrestima la pérdida en mantos gruesos y la subestima en
mantos finos. Es un supuesto a discutir en el informe.

2) Nieve natural
----------------
Open-Meteo da la nieve caída en cm de nieve fresca (0,7 cm por mm de agua).
Se pasa a agua equivalente y luego a m³ de nieve pisada (densidad 450 kg/m³)
sobre la superficie del sector (area_m2 de pistas.csv; si aún no existe, Z
queda vacío).

3) Nieve inicial
----------------
S0_p = 0: el 15 de noviembre se supone que no hay base de nieve en pista.

Fuentes
-------
- Factor grado-día de la nieve: valores típicos de 2 a 6 mm/(°C·d), que
  convergen a 3-5 en mantos profundos (Hock, 2003; revisión en HESS 2026).
- Evaposublimación en Sierra Nevada: 24-33 % de la ablación anual a 2500 m
  (Refugio Poqueira), con máximos de 0,49 mm/h y presente el 60 % del tiempo
  con nieve (Herrero y Polo, 2016, The Cryosphere 10, 2981-2998).

Uso:  python src/snow_physics.py     (después de process_weather.py)
"""

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "weather"
SCEN_DIR = ROOT / "data" / "processed" / "scenarios"
PISTAS_FILE = ROOT / "data" / "processed" / "pistas.csv"
POSITIONS_FILE = ROOT / "data" / "processed" / "positions.csv"
POSITIONS_PROVISIONAL = ROOT / "data" / "interim" / "positions_provisional.csv"

# ----------------------------------------------------------------------------
# Parámetros (supuestos documentados -> sensibilidad en S-A3)
# ----------------------------------------------------------------------------
REF_ELEVATION_M = 2500
LAPSE_RATE = -0.65 / 100        # °C / m
T_MELT = 0.0                    # umbral de fusión (°C)
DDF = 4.0                       # mm w.e. / (°C · día)
SUBL = 1.0                      # evaposublimación, mm w.e. / día (constante)
H_REF = 0.5                     # espesor de referencia del manto pisado (m)
RHO_GROOMED = 0.45              # densidad nieve pisada / densidad agua
SWE_REF = H_REF * RHO_GROOMED * 1000     # = 225 mm w.e.
CM_SNOW_PER_MM_WATER = 0.7      # conversión que usa Open-Meteo para "snowfall"


def sector_altitudes() -> pd.Series:
    """Cota de cada sector p = media de las cotas de sus posiciones."""
    path = POSITIONS_FILE if POSITIONS_FILE.exists() else POSITIONS_PROVISIONAL
    pos = pd.read_csv(path)
    return pos.groupby("p")["altitude_m"].mean()


def sector_areas() -> pd.Series | None:
    pistas = pd.read_csv(PISTAS_FILE)
    if "area_m2" not in pistas.columns:
        print("AVISO: pistas.csv no tiene area_m2 -> Z se deja vacío por ahora")
        return None
    return pistas.set_index("p")["area_m2"]


def snow_for_season(df: pd.DataFrame, alt: pd.Series, area: pd.Series | None) -> pd.DataFrame:
    start = pd.Timestamp(f"{df['season'].iloc[0]}-11-15")
    df = df.assign(d=((df["datetime"] - start).dt.total_seconds() // 86400).astype(int))

    rows = []
    for p, z in alt.items():
        T = df["temperature_2m"] + LAPSE_RATE * (z - REF_ELEVATION_M)
        pdd = np.maximum(T.groupby(df["d"]).mean() - T_MELT, 0)        # °C·día
        loss_mm = DDF * pdd + SUBL
        delta = (loss_mm / SWE_REF).clip(upper=1.0)

        snow_cm = df.groupby("d")["snowfall"].sum()
        if area is not None:
            swe_m = snow_cm / CM_SNOW_PER_MM_WATER / 1000            # m de agua
            Z = swe_m * area[p] / RHO_GROOMED                        # m³ nieve pisada
        else:
            Z = pd.Series(np.nan, index=snow_cm.index)

        rows.append(pd.DataFrame({"p": p, "d": delta.index, "PDD": pdd.values,
                                  "Delta": delta.values, "Z": Z.values}))
    return pd.concat(rows, ignore_index=True).round(4)


def main() -> None:
    alt, area = sector_altitudes(), sector_areas()
    summary = []
    for f in sorted(RAW_DIR.glob("weather_*.csv")):
        df = pd.read_csv(f, parse_dates=["datetime"])
        season = int(df["season"].iloc[0])
        snow = snow_for_season(df, alt, area)
        out = SCEN_DIR / f"{season}_{season + 1}"
        out.mkdir(parents=True, exist_ok=True)
        snow[["p", "d", "Delta", "Z"]].to_csv(out / "snow.csv", index=False)
        # % de la nieve que queda tras todo el horizonte si no se añadiera nada
        surv = snow.groupby("p")["Delta"].apply(lambda x: np.prod(1 - x)).mean()
        summary.append((f"{season}/{season + 1}", round(snow["Delta"].mean() * 100, 2),
                        round(surv * 100, 1)))

    pd.DataFrame({"p": alt.index, "S0": 0.0}).to_csv(
        ROOT / "data" / "processed" / "initial_snow.csv", index=False)

    print(pd.DataFrame(summary, columns=["temporada", "pérdida media %/día",
                                         "% que sobrevive 53 días"]).to_string(index=False))
    print("Listo: snow.csv en cada escenario e initial_snow.csv")


if __name__ == "__main__":
    main()
