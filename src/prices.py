"""
B5. precio de la electricidad por bloque de 3 h -> data/processed/prices.csv (t, Pi)

Fuente: OMIE, precio marginal del mercado diario, zona españa

Periodo de referencia: 15/11/2025-6/1/2026

El día d del modelo, usa el precio del mismo día de esa temporada. Se usa la misma serie en todos los escenarios climáticos (supuesto nuestro).

Π_t [€/kWh] = media del precio OMIE en las 3 horas del bloque / 1000  +  ADDER
    ADDER = peajes, cargos y margen de comercializadora (supuesto, constante).
"""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import requests


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "omie"
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"

START_REF = date(2025, 11, 15)          #día d = 0 en la temporada de referencia
N_DAYS = 53
BLOCKS_PER_DAY = 8                      #bloques de 3h -> t = 8*d + bloque (como periods.csv)
ADDER = 0.04                            #€/kWh, supuesto -> sensibilidad (S-B3)

URL = "https://www.omie.es/es/file-download?parents%5B0%5D=marginalpdbc&filename=marginalpdbc_{}"

def download_day(f: date) -> Path:
    """Descarga el fichero de cada día. OMIE a veces republica un día corregido como versión .2 o .3: se prueba en orden"""
    RAW.mkdir(parents=True, exist_ok=True) #los vamos a guardar toods por si acaso
    for v in (1,2,3): #probamos con distintas verisiones
        path = RAW/ f"marginalpdbc_{f:%Y%m%d}.{v}"
        if path.exists():
            return path 
    for v in (1,2,3):
        r = requests.get(URL.format(f"{f:%Y%m%d}.{v}"), timeout=30)
        if r.ok and r.content.startswith(b"MARGINALPDBC"):
            path = RAW / f"marginalpdbc_{f:%Y%m%d}.{v}"
            path.write_bytes(r.content)
            return path
    raise RuntimeError(f"No se encuentra el fichero OMIE del {f} (versiones .1 a .3)")

def read_day(path: Path) -> list[float]:
    """Devolvemos los 24 precios horarios de España (euros/MWh) de un fichero OMIE.
    Formato de cada línea de datos: año;mes;día;periodo;precio_PT;precio_ES;"""

    prices = []
    for line in path.read_text(encoding="latin-1").splitlines():
        parts = line.strip().split(";")
        if len(parts)>=6 and parts[0].isdigit():
            prices.append(float(parts[5].replace(",", ".")))

    per_hour = len(prices) // 24 #1 (si horario) o 4 (cuartohorario)
    if per_hour not in (1,4) or len(prices) %24:
        raise ValueError(f"{path.name}: {len(prices)} periodos, formato inesperado")
    return [sum(prices[h* per_hour:(h+1)* per_hour]) / per_hour for h in range(24)]

if __name__ == "__main__":
    hourly, rows = [], []
    for d in range(N_DAYS):
        f = START_REF + timedelta(d)
        h_prices = read_day(download_day(f))
        hourly += [{"d": d, "fecha_ref": f.isoformat(), "hora": h, "eur_MWh": p}
                   for h, p in enumerate(h_prices)]
        for blk in range(BLOCKS_PER_DAY):
            omie = sum(h_prices[3 * blk:3 * blk + 3]) / 3          # €/MWh, media del bloque
            rows.append({"t": BLOCKS_PER_DAY * d + blk, "Pi": round(omie / 1000 + ADDER, 5)})

    INTERIM.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(hourly).to_csv(INTERIM / "omie_horario.csv", index=False)
    prices = pd.DataFrame(rows)
    prices.to_csv(PROCESSED / "prices.csv", index=False)
    print(f"prices.csv: {len(prices)} bloques | Pi medio {prices.Pi.mean():.4f} €/kWh "
          f"(min {prices.Pi.min():.4f}, max {prices.Pi.max():.4f})")