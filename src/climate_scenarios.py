"""
climate_scenarios.py  —  Persona A, tarea A6: escenarios climáticos.

1) Temporadas representativas (de las 10 descargadas)
-----------------------------------------------------
Criterio único: nieve que puede producir un cañón de ventilador en la
temporada (media de las posiciones). Es lo que condiciona las decisiones del
modelo, porque combina frío y horas sin viento.
    FRIA    2020/21 -> máxima producción (42.800 m³/cañón) y más nieve natural
    NORMAL  2019/20 -> cerca de la mediana (29.000 vs 27.600 m³/cañón) y nieve
                       natural típica. 2015/16 está igual de cerca de la
                       mediana, pero casi no nevó (1,5 cm): no es representativa.
    CALIDA  2022/23 -> mínima producción (16.000 m³/cañón).
                       (2023/24 es la más cálida en temperatura y pérdidas,
                       pero produce algo más: 19.400 m³/cañón.)

2) Escenarios de calentamiento
------------------------------
Sobre la temporada NORMAL se suma +1 °C y +2 °C a todas las horas:
- La humedad relativa se mantiene (supuesto) y se recalcula el bulbo húmedo.
- La nieve natural de las horas que pasan a estar por encima de 0 °C se
  convierte en lluvia (umbral de fase de 0 °C, el más usado en la literatura).
- El umbral de viento es el mismo de las 10 temporadas (no cambia con la T).
Es un "delta change" sencillo: no cambia la frecuencia de temporales ni la
humedad, solo desplaza la temperatura. Limitación a comentar en el informe.

Salidas: data/processed/scenarios/<escenario>/production.csv y snow.csv para
    fria, normal, calida, normal_plus1, normal_plus2
y data/processed/scenarios/scenarios.csv con la tabla de escenarios.

Uso:  python src/climate_scenarios.py   (después de process_weather.py)
"""

import shutil

import pandas as pd

import process_weather as pw
import snow_physics as sp

REPRESENTATIVE = {"fria": 2020, "normal": 2019, "calida": 2022}
WARMING = {"normal_plus1": 1.0, "normal_plus2": 2.0}
RAIN_THRESHOLD_C = 0.0


def copy_season(label: str, season: int) -> None:
    """Las temporadas representativas ya están calculadas: se copian."""
    src = pw.SCEN_DIR / f"{season}_{season + 1}"
    dst = pw.SCEN_DIR / label
    dst.mkdir(parents=True, exist_ok=True)
    for f in ["production.csv", "snow.csv"]:
        shutil.copy(src / f, dst / f)


def warmed_season(season: int, dT: float) -> pd.DataFrame:
    """Datos horarios de la temporada con +dT °C y la nieve convertida en lluvia
    cuando la temperatura pasa a estar por encima del umbral."""
    df = pd.read_csv(pw.RAW_DIR / f"weather_{season}_{season + 1}.csv",
                     parse_dates=["datetime"])
    df["temperature_2m"] = df["temperature_2m"] + dT
    df.loc[df["temperature_2m"] > RAIN_THRESHOLD_C, "snowfall"] = 0.0
    return df


def main() -> None:
    rows = []
    for label, season in REPRESENTATIVE.items():
        copy_season(label, season)
        rows.append((label, f"{season}/{season + 1}", 0.0))

    pos = pw.load_positions()
    wind_thr = pw.wind_threshold_all_seasons()
    alt, area = sp.sector_altitudes(), sp.sector_areas()
    base = REPRESENTATIVE["normal"]

    for label, dT in WARMING.items():
        raw = warmed_season(base, dT)
        blocks = pw.to_blocks(pw.hourly_by_position(pw.add_time_indices(raw), pos, wind_thr))
        pw.write_production(blocks, label=label)
        snow = sp.snow_for_season(raw, alt, area)
        snow[["p", "d", "Delta", "Z"]].to_csv(pw.SCEN_DIR / label / "snow.csv", index=False)
        rows.append((label, f"{base}/{base + 1}", dT))

    table = pd.DataFrame(rows, columns=["escenario", "temporada_base", "dT"])
    # Resumen para comprobar: producción por cañón, % bloques aptos y pérdida media
    summ = []
    for label in table["escenario"]:
        prod = pd.read_csv(pw.SCEN_DIR / label / "production.csv")
        fan = prod[prod["k"] == "FAN"]
        snow = pd.read_csv(pw.SCEN_DIR / label / "snow.csv")
        summ.append((round(fan.groupby("j")["G"].sum().mean()),
                     round(100 * fan["A"].mean(), 1),
                     round(100 * snow["Delta"].mean(), 2)))
    table[["prod_FAN_m3_por_canon", "pct_bloques_aptos_FAN", "perdida_media_pct_dia"]] = summ
    table.to_csv(pw.SCEN_DIR / "scenarios.csv", index=False)
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
