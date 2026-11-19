"""
Aquí están las curvas de producción y los consumos de las dos tecnologías.
Todo lo que el modelo necesita de cada equipo sale de aquí:
    G_{j,k,t}  nieve por equipo y bloque (m³)
    E_{j,k,t}  energía por equipo y bloque (kWh)  = KWH_PER_M3[k] * G_{j,k,t}
    PHI        agua por m³ de nieve

Fuentes
-------
FAN (cañón de ventilador):
  - Curva de producción aproximada a partir de las fichas de Bachler SnoTek:
    ~21 m³/h a -1,5 °C de bulbo húmedo, ~35 m³/h a -3 °C, ~67 m³/h a -5 °C
    y hasta ~115-124 m³/h con el equipo completo a temperaturas bajas.
    Nosotros arrancamos en -2 °C (umbral del modelo) y limitamos a 100 m³/h.
  - Consumo: 1-2 kWh/m³ para cañones de ventilador (incluye bombeo) -> 1,5.
  - Pérdidas de agua durante la producción en ventiladores: 5-15 %
    (Grünewald y Wolfsperger, 2019; Olefs et al., 2010) -> 10 %.
AW (TechnoAlpin SnowFactory 210):
  - 208 m³ de nieve / 24 h con ~180 kW (ficha técnica, aire a 15 °C).
    -> 26 m³ por bloque de 3 h y 540 kWh por bloque (~20,8 kWh/m³).
  - "Produce nieve independientemente de la temperatura del aire":
    no se limita por frío ni por viento (está dentro de un contenedor).
  - 450 l de agua = 1 m³ de nieve.

Supuestos
---------
- La curva FAN es la de un equipo "medio"; en la realidad cada modelo es
  distinto. Es un parámetro de sensibilidad.
- La producción AW se toma constante (nominal). Con aire más frío rendiría
  algo más, así que es una estimación conservadora.
- La energía es proporcional a la nieve producida (la mayor parte del consumo
  es bombear y presurizar el agua), por eso E depende de (j,k,t).
"""

import numpy as np

TECHS = ["FAN", "AW"]

# --- Curva de producción del ventilador: (bulbo húmedo °C, m³ nieve / h) ---
# Interpolación lineal entre puntos; 0 por encima de -2 °C.
FAN_CURVE_TW = np.array([-12.0, -8.0, -5.0, -3.0, -2.0])
FAN_CURVE_M3H = np.array([100.0, 100.0, 67.0, 35.0, 20.0])

AW_M3_PER_HOUR = 208 / 24          # ≈ 8,67 m³/h

KWH_PER_M3 = {"FAN": 1.5, "AW": 180 * 24 / 208}   # AW ≈ 20,8 kWh/m³

WATER_M3_PER_M3_SNOW = 0.45        # 450 l de agua por m³ de nieve
FAN_PRODUCTION_LOSSES = 0.10       # 10 % del agua no llega a la pista
# PHI = agua captada por m³ de nieve que llega a la pista
PHI = {"FAN": WATER_M3_PER_M3_SNOW / (1 - FAN_PRODUCTION_LOSSES),   # 0,50
       "AW": WATER_M3_PER_M3_SNOW}                                 # 0,45


def fan_production_m3h(Tw):
    """Nieve (m³/h) de un cañón de ventilador en función del bulbo húmedo.
    Devuelve 0 si Tw > -2 °C. Para Tw < -12 °C se mantiene el máximo."""
    Tw = np.asarray(Tw, dtype=float)
    g = np.interp(Tw, FAN_CURVE_TW, FAN_CURVE_M3H)   # fuera del rango: extremos
    return np.where(Tw > -2.0, 0.0, g)
