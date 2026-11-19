"""
Genera los parámetros de las restricciones R5 (balsa), R6 (concesión) y R7
(caudal y energía máximos por bloque):

    data/processed/water_energy.yaml   B_MAX, B0, W, Q_MAX, E_MAX, PHI_FAN, PHI_AW
    data/processed/inflow.csv          d, I     (aporte diario a la balsa, m³)

Fuentes
-------
- Concesión de la CHG: 350.000 m³/año del río Monachil para producir nieve,
  vigente desde 2007 y prorrogada hasta 2026 (Público; La Política Online).
  Cetursa pidió ampliarla a 725.749 m³/año (BOE-B-2023-35624) -> escenario de
  sensibilidad "concesión doblada".
- Balsas: el agua del río Monachil se bombea con cuatro estaciones de bombeo
  a dos balsas de 100.000 m³ cada una en Borreguiles (memoria técnica de
  Cetursa, i-02-memoria-técnica-0289-19).
- Captación: caudal concesional de 65 l/s (BOE-B-2023-35624) = 5.616 m³/día.
  Es la ENTRADA máxima del río a las balsas (I_d). Coincide con los
  ~5.000 m³/día (~58 l/s) del informe de CCOO (eldiario.es, 2022), que por
  tanto miden la entrada desde el río, no la salida hacia los cañones.
- Distribución (balsas -> cañones), Q_MAX: no hay dato público. Las balsas
  existen para llenarse despacio (24 h) y vaciarse deprisa cuando hace frío,
  así que la red de distribución es mayor que la captación. Supuesto: el
  doble de la captación medida (2 x 5.000 m³/día ≈ 116 l/s), del orden de lo
  que transporta una tubería DN250 (la de la red de nieve de Cetursa) a
  ~2,4 m/s (≈ 118 l/s). Sensibilidad en water_pareto.py.

Supuestos
---------
- OMEGA: fracción de la concesión anual que se gasta en el horizonte
  (15 nov - 6 ene). La producción se concentra al principio de temporada
  (hasta mediados de diciembre se fabrica la base) -> 0,7.
- B0: balsas llenas el 15 de noviembre (se llenan en otoño).
- Aporte I_d: lo máximo que se puede captar al día (caudal concesional). R5
  es "<=", así que el modelo capta menos si no le hace falta; el total del
  horizonte lo limita W (R6).
- E_MAX: no hay datos públicos de la potencia contratada. Se pone una potencia
  holgada (10 MW) y se comprueba en los resultados si llega a limitar.
"""

from pathlib import Path

import pandas as pd

from snowmaking import PHI

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed"

N_DAYS = 53                     # 15 nov - 6 ene
BLOCKS_PER_DAY = 8              # bloques de 3 h

ANNUAL_CONCESSION = 350_000     # m³/año (CHG)
OMEGA = 0.7                     # fracción usada en el horizonte (supuesto)
B_MAX = 2 * 100_000             # m³, dos balsas de 100.000 m³ (memoria técnica Cetursa)
B0 = B_MAX                      # balsas llenas al inicio (supuesto)
CONCESSION_FLOW_LS = 65         # l/s, caudal concesional (BOE) -> entrada máxima I_d
DAILY_INTAKE_MEASURED = 5_000   # m³/día que se captan (CCOO, 2022) ≈ 58 l/s
DISTRIBUTION_FACTOR = 2.0       # red de distribución = 2 x captación (supuesto, ver water_pareto.py)
POWER_MAX_KW = 10_000           # potencia máxima disponible (supuesto, holgado)


def main() -> None:
    params = {
        "B_MAX": B_MAX,
        "B0": B0,
        "W": round(OMEGA * ANNUAL_CONCESSION),
        "Q_MAX": DISTRIBUTION_FACTOR * DAILY_INTAKE_MEASURED / BLOCKS_PER_DAY,  # m³ por bloque
        "E_MAX": POWER_MAX_KW * 24 / BLOCKS_PER_DAY,       # kWh por bloque
        "PHI_FAN": round(PHI["FAN"], 4),
        "PHI_AW": round(PHI["AW"], 4),
    }
    with open(OUT / "water_energy.yaml", "w", encoding="utf-8") as f:
        f.write("# Parámetros de agua y energía (src/water.py)\n")
        for k, v in params.items():
            f.write(f"{k}: {v}\n")

    inflow = CONCESSION_FLOW_LS * 86_400 / 1000            # m³/día
    pd.DataFrame({"d": range(N_DAYS), "I": round(inflow, 1)}).to_csv(
        OUT / "inflow.csv", index=False)

    for k, v in params.items():
        print(f"{k:8s} = {v}")
    print(f"I_d      = {inflow:.0f} m³/día")
    print(f"Agua máxima disponible en el horizonte: B0 + suma(I_d) = "
          f"{B0 + inflow * N_DAYS:,.0f} m³ (pero la concesión W limita a {params['W']:,} m³)")


if __name__ == "__main__":
    main()
