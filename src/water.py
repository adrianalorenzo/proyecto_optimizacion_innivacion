"""
water.py  —  Persona A, tarea A5: datos de agua y energía.

Genera los parámetros de las restricciones R5 (balsa), R6 (concesión) y R7
(caudal y energía máximos por bloque):

    data/processed/water_energy.yaml   B_MAX, B0, W, Q_MAX, E_MAX, PHI_FAN, PHI_AW
    data/processed/inflow.csv          d, I     (aporte diario a la balsa, m³)

Están en ficheros propios (no en scalars.yaml) para no editar ficheros de B.

Fuentes
-------
- Concesión de la CHG: 350.000 m³/año del río Monachil para producir nieve,
  vigente desde 2007 y prorrogada hasta 2026 (Público; La Política Online).
  Cetursa pidió ampliarla a 725.749 m³/año (BOE-B-2023-35624) -> escenario de
  sensibilidad "concesión doblada".
- Balsas: "dos lagos artificiales de 100.000 m³ de capacidad que actúa como
  reserva de las captaciones del río" (Cetursa, JTTCIA 2013). No queda claro si
  son 100.000 m³ cada uno o en total: tomamos 2 x 100.000 (lectura natural) y
  lo marcamos como supuesto.
- Uso de agua: unos 5 millones de litros al día para fabricar nieve (informe
  de CCOO, eldiario.es, feb. 2022) -> lo usamos como caudal máximo operativo.

Supuestos (sensibilidad en S-A2 / S-A3)
---------------------------------------
- OMEGA: fracción de la concesión anual que se gasta en el horizonte
  (15 nov - 6 ene). La producción se concentra al principio de temporada
  (hasta mediados de diciembre se fabrica la base) -> 0,7.
- B0: balsas llenas el 15 de noviembre (se llenan en otoño).
- Aporte I_d: la concesión se capta repartida de forma uniforme en la
  temporada de captación invernal (nov - abr, ~180 días).
- E_MAX: no hay datos públicos de la potencia contratada. Se pone una potencia
  holgada (10 MW) y se comprueba en los resultados si llega a limitar. Con el
  caudal máximo de 5.000 m³/día, el agua limita mucho antes que la energía.
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
B_MAX = 2 * 100_000             # m³, dos balsas de 100.000 m³ (supuesto de lectura)
B0 = B_MAX                      # balsas llenas al inicio (supuesto)
CAPTURE_DAYS = 180              # días de captación invernal (nov-abr)
DAILY_WATER_USE_MAX = 5_000     # m³/día (CCOO, 2022) -> caudal máximo operativo
POWER_MAX_KW = 10_000           # potencia máxima disponible (supuesto, holgado)


def main() -> None:
    params = {
        "B_MAX": B_MAX,
        "B0": B0,
        "W": round(OMEGA * ANNUAL_CONCESSION),
        "Q_MAX": DAILY_WATER_USE_MAX / BLOCKS_PER_DAY,     # m³ de agua por bloque
        "E_MAX": POWER_MAX_KW * 24 / BLOCKS_PER_DAY,       # kWh por bloque
        "PHI_FAN": round(PHI["FAN"], 4),
        "PHI_AW": round(PHI["AW"], 4),
    }
    with open(OUT / "water_energy.yaml", "w", encoding="utf-8") as f:
        f.write("# Parámetros de agua y energía (Persona A, src/water.py)\n")
        for k, v in params.items():
            f.write(f"{k}: {v}\n")

    inflow = ANNUAL_CONCESSION / CAPTURE_DAYS
    pd.DataFrame({"d": range(N_DAYS), "I": round(inflow, 1)}).to_csv(
        OUT / "inflow.csv", index=False)

    for k, v in params.items():
        print(f"{k:8s} = {v}")
    print(f"I_d      = {inflow:.0f} m³/día")
    print(f"Agua máxima disponible en el horizonte: B0 + suma(I_d) = "
          f"{B0 + inflow * N_DAYS:,.0f} m³ (pero la concesión W limita a {params['W']:,} m³)")


if __name__ == "__main__":
    main()
