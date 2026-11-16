"""
B4: ingresos R_{p,d} (revenue.csv) y días clase con km mínimos L_d

Idea. R_{p,d} = N_d* PRECIO_d * FACTOR_INGRESO * peso_p

    N_d: esquiadores potenciales del día d si toda la zona modelada está abierta
    PRECIO_d: forfait de 1 día adulto según el tipo de día (tarifas oficiales 2025/26)
    FACTOR_INGRESO: ingreso medio por esquiador / precio del forfait de día
    peso_p: capcidad de remontes del sector p / capacidad total de los 17 sectores
"""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
INTERIM = ROOT / "data" / "interim"


#calendario

START = date(2026, 11, 15)
N_DAYS = 53                                    #15/11-6/1

FESTIVOS = {date(2026, 12, 7), date(2026, 12, 8),   #constitución (trasladado) e Inmaculada
            date(2026, 12, 25), date(2027, 1, 1), date(2027, 1, 6)}
PUENTE = {date(2026, 12, 5) + timedelta(i) for i in range(4)}           #5/12 - 8/12
NAVIDAD = {date(2026, 12, 23) + timedelta(i) for i in range(15)}         # 23/12 - 6/1 (vacaciones escolares)

#supuestos 

#esquiadores potenciales por tipo de día (toda la zona modelada abierta)
#referencia: puente de diciembre 2025 = 5400/6200/3800 esquiadores con solo 20 km abiertos

SKIERS = {"laborable": 1500, "fin_de_semana": 4500, "navidad": 6000, "punta": 7000}

#forfait 1 día adulto 2025/26 (web oficial): tarifa 4 = 52 €, tarifa 2 = 57 €, tarifa 1 = 60 €.
PRICE = {"laborable": 52.0, "fin_de_semana": 57.0, "navidad": 60.0, "punta": 60.0}

FACTOR_INGRESO = 0.75          #supuesto -> análisis de sensibilidad

#Días clave D^C y km mínimos L_d (compromiso comercial, restricción blanda R4).
#Puente: 20 km, lo que abrió la estación en el puente de 2025. Navidad-Reyes: 30 km.
L_PUENTE, L_NAVIDAD = 20.0, 30.0
KEY_NAVIDAD = {date(2026, 12, 26) + timedelta(i) for i in range(12)}     #26/12- 6/1

def day_type(f: date) -> str:
    """Clasifica cada día del horizonte en uno de los 4 tipos de demanda."""
    if f in PUENTE or f in FESTIVOS or (f in NAVIDAD and f.weekday() >=5):
        return "punta"
    if f in NAVIDAD:
        return "navidad"

    if f.weekday() >=5:
        return "fin_de_semana"
    return "laborable"

def build_calendar() -> pd.DataFrame:
    rows = []
    for d in range(N_DAYS):
        f = START+timedelta(d)
        tipo = day_type(f)
        rows.append({"d": d, "fecha": f.isoformat(), "dia_semana": f.strftime("%a"),
                     "tipo": tipo, "esquiadores": SKIERS[tipo], "precio": PRICE[tipo]})
    return pd.DataFrame(rows)


def build_revenue(cal: pd.DataFrame, pistas: pd.DataFrame) -> pd.DataFrame:
    peso = pistas.set_index("p")["lift_capacity"] / pistas["lift_capacity"].sum()
    ingreso_dia = cal.set_index("d")["esquiadores"] * cal.set_index("d")["precio"] * FACTOR_INGRESO
    rows = [{"p": p, "d": d, "R": round(ingreso_dia[d] * peso[p], 2)}
            for p in pistas["p"] for d in cal["d"]]
    return pd.DataFrame(rows)


def build_keydays(cal: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for d, f in zip(cal["d"], pd.to_datetime(cal["fecha"]).dt.date):
        if f in PUENTE:
            rows.append({"d": d, "L": L_PUENTE})
        elif f in KEY_NAVIDAD:
            rows.append({"d": d, "L": L_NAVIDAD})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    pistas = pd.read_csv(PROCESSED / "pistas.csv")
    cal = build_calendar()
    revenue = build_revenue(cal, pistas)
    keydays = build_keydays(cal)

    INTERIM.mkdir(parents=True, exist_ok=True)
    cal.to_csv(INTERIM / "calendario_demanda.csv", index=False)     # para revisar y para el informe
    revenue.to_csv(PROCESSED / "revenue.csv", index=False)
    keydays.to_csv(PROCESSED / "keydays.csv", index=False)

    print(f"revenue.csv: {len(revenue)} filas | ingreso máximo del horizonte "
          f"(todo abierto): {revenue['R'].sum():,.0f} €")
    print(f"keydays.csv: {len(keydays)} días clave")




