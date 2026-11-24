# Innivación artificial en Sierra Nevada — MILP

Proyecto final de **Optimización y Simulación** (3.º del Grado en Ingeniería Matemática e
Inteligencia Artificial, Comillas ICAI), curso 2026/27.

Autoras: **Adriana Lorenzo Mingorance** y **Jimena Zubizarreta Gómez**.

Este repositorio contiene el informe (`informe.pdf`), el código, los datos y los resultados del
proyecto. Las secciones citadas abajo (2, 3.x, 4.x) se refieren al informe.

## Qué hace el modelo

Un único modelo de programación lineal entera mixta (Pyomo + Gurobi) que, desde el punto de
vista de la estación (Cetursa), maximiza el beneficio entre el 15 de noviembre y el 6 de enero
(53 días, 424 bloques de 3 horas). Decide:

- cuántos equipos de producción de nieve funcionan en cada posición, tecnología y bloque;
- qué sectores abren cada día (17 sectores: 11 actuales y 6 de ampliación);
- en el modo de inversión, qué posiciones nuevas habilitar (20 candidatas) y cuántos equipos
  de cada tecnología instalar: cañones de ventilador (FAN) o *all-weather* (AW).

Respeta el frío y el viento disponibles, el agua (concesión, balsas, captación y caudal), la
potencia eléctrica, la red de accesos entre sectores, los kilómetros comprometidos en los días
clave (restricción blanda) y el presupuesto. Tiene dos modos:

- **(a) Operación:** con los equipos actuales; las variables de inversión `u` y `n` se fijan a 0.
- **(b) Inversión:** además decide las posiciones y los equipos nuevos.

El consumo de agua se estudia como segundo objetivo mediante la ε-restricción.

---

## 1. Instalación

```bash
pip install -r requirements.txt
```

- **Python:** se ha usado Python 3.13.
- **Solver:** todos los resultados del informe se han obtenido con **Gurobi** (licencia
  académica, paquete `gurobipy`). La licencia gratuita de `gurobipy` está limitada en tamaño y
  no basta para este modelo (unas 28.000 variables). Si Gurobi no está disponible, el código
  usa **HiGHS** (`highspy`, incluido en `requirements.txt`), pero no se ha comprobado con el
  modelo completo y los tiempos serán mucho mayores. El orden de preferencia está en
  `src/test_model_a.py` (`pick_solver`) y se puede forzar con `--solver gurobi|highs`.
- En Windows, si Pyomo no encuentra Gurobi, hay que ejecutar con el Python que tiene
  `gurobipy` (en nuestro caso, `py -3.13 ...`).
- **No hace falta internet:** los datos meteorológicos (ERA5 vía Open-Meteo), los precios de
  OMIE y el plano de pistas ya están en `data/raw/`.

## 2. Reproducir los resultados

```bash
python run_all.py                 # todo: datos + casos base + experimentos + figuras
python run_all.py --skip-data     # sin regenerar los datos (usa data/processed tal cual)
python run_all.py --only-plots    # solo rehace las figuras a partir de results/
```

**Importante:** `results/` ya contiene los resultados de la ejecución completa del 22/11/2026,
que son los que aparecen en el informe. Volver a ejecutar `run_all.py` los sobrescribe. Como
algunas resoluciones de inversión se detienen por el límite de tiempo y hay planes de inversión
casi equivalentes, una nueva ejecución puede dar cifras ligeramente distintas.

**Tiempo de ejecución.** La ejecución completa resuelve el modelo unas 85 veces y tarda unas
4 h 40 min con Gurobi en un portátil (ejecución del 22/11/2026, con el equipo libre):

| Paso | Resoluciones | Tiempo |
|---|---|---|
| Datos y casos base (operación con x entera y continua, inversión) | 3 | 8 min |
| `climate_runs.py --mode operation` | 5 | 1 min |
| `water_pareto.py` | 15 | 5 min |
| `sensitivity_physics.py` (incluye la validación) | 21 | 14 min |
| `climate_runs.py --mode investment` | 5 | 31 min |
| `budget_sweep.py` | 9 | 32 min |
| `aw_price_breakeven.py` | 21 | 2 h 48 min |
| `electricity_shock.py` | 6 | 19 min |

Los experimentos usan `--relax-x` (ver §7). Cada resolución tiene un límite de tiempo
(`--time-limit`, 600 s por defecto); si se alcanza, se guarda la mejor solución encontrada y
su *gap* aparece en la columna `gap` de los CSV. Conviene ejecutar con el ordenador enchufado y
sin suspensión: Gurobi mide el tiempo real, y una suspensión a mitad de una resolución la
detiene por límite de tiempo.

Un caso suelto:

```bash
python src/solve.py --scenario normal --mode operation              # x entera
python src/solve.py --scenario normal --mode investment --relax-x   # x continua
# opciones: --days N (recortar horizonte), --gap 0.01, --time-limit 600, --solver gurobi|highs
# escenarios: fria, normal, calida, normal_plus1, normal_plus2
```

## 3. Resultados ↔ informe

| Sección del informe | Qué muestra | Fichero en `results/` |
|---|---|---|
| 4.1 Validación | x entera frente a continua; pruebas de validación | `normal_operation/`, `normal_operation_relax/`, `experiments/validation.csv` |
| 4.2 Caso base de operación | operación en la temporada normal | `normal_operation/` |
| 4.3 Sensibilidad al clima | operación en los cinco escenarios | `experiments/climate_operation.csv` |
| 4.4 Sensibilidad al agua | concesión, caudal y frontera beneficio–agua | `experiments/water_concession.csv`, `water_flow.csv`, `water_pareto.csv` |
| 4.5 Supuestos físicos | pérdidas, viento, horas aptas, rendimiento | `experiments/sensitivity_physics.csv` |
| 4.6 Caso base con inversión | inversión con Ψ = 3 M€, presupuesto y climas | `normal_investment_relax/`, `experiments/budget_sweep*.csv`, `climate_investment.csv` |
| 4.7 Precio del *all-weather* | equipos AW comprados según su precio | `experiments/aw_price_breakeven.csv` |
| 4.8 Supuestos económicos | electricidad +30 %, θ y M_KM | `experiments/economic_sensitivity.csv` |

Cada carpeta `results/<escenario>_<modo>[_relax]/` contiene un CSV por variable (`x`, `y`,
`s`, `b`, `u`, `n`, `h`) y `summary.json` con los indicadores (beneficio real, agua usada,
km incumplidos, tiempo, *gap*…). Las figuras del informe están en `results/figures/`.

## 4. Flujo de datos

```
Clima, nieve y agua
  weather.py            ERA5 horario (Open-Meteo)              -> data/raw/weather/
  process_weather.py    cota, bulbo húmedo, viento, aptitud,
                        bloques de 3 h                         -> data/interim/weather_blocks.csv
  snowmaking.py         curvas de producción por tecnología,
                        kWh/m³, Φ_k  (lo importan los demás)
  snow_physics.py       pérdidas Δ (grado-día + evaposublimación), nieve natural Z
  climate_scenarios.py  temporadas fría / normal / cálida, +1 °C, +2 °C (delta change)
                                                               -> data/processed/scenarios/
  water.py              concesión, balsas, Q_MAX, entrada diaria -> water_energy.yaml, inflow.csv

Estación, economía e inversión
  (a mano)              plano de Cetursa 2025 y fuentes del informe
                                                               -> pistas.csv, access.csv, positions.csv,
                                                                  tech.csv, economics.yaml
  economics.py          calendario de demanda, ingresos R, días clave
                                                               -> revenue.csv, keydays.csv,
                                                                  interim/calendario_demanda.csv
  prices.py             OMIE cuartohorario -> horario -> bloque de 3 h + 0,04 €/kWh
                                                               -> prices.csv

Modelo
  load_data.py          junta todo lo anterior en un diccionario de datos
  model.py              conjuntos, parámetros, variables, capacity()
  constraints_a.py      restricciones de nieve y agua
  constraints_b.py      objetivo y restricciones de estación e inversión
  solve.py              resuelve un escenario y exporta resultados e indicadores
  plots.py              figuras del informe
```

Los ficheros hechos a mano de `data/processed/` (`pistas.csv`, `access.csv`, `positions.csv`,
`tech.csv`, `economics.yaml`) no se regeneran con ningún script: son necesarios para ejecutar
el modelo.

## 5. Restricciones ↔ código

| Restricción | Qué representa | Dónde |
|---|---|---|
| Objetivo | ingresos − coste eléctrico − inversión imputada − M_KM · km incumplidos en días clave | `constraints_b.py` |
| R1 | solo funcionan equipos instalados y en bloques aptos (x ≤ A·(N0 + n)) | `constraints_a.py` |
| R2 | balance de nieve acumulada de cada sector (pérdidas Δ, nieve natural Z, producción G·x) | `constraints_a.py` |
| R3a | abrir un sector exige nieve suficiente | `constraints_b.py` |
| R3b | abrir un sector exige que su acceso esté abierto (red de pistas) | `constraints_b.py` |
| R4 | km mínimos abiertos en los días clave (blanda, holgura h_d) | `constraints_b.py` |
| R5 | balance de las balsas (captación ≤ I_d; B_MAX como cota de b) | `constraints_a.py` |
| R6 | concesión de agua del horizonte / límite ε (`W_EPS`) | `constraints_a.py` |
| R7 | energía (E_MAX) y caudal (Q_MAX) máximos por bloque | `constraints_a.py` |
| R8 | solo se instala en posiciones candidatas habilitadas | `constraints_b.py` |
| R9 | presupuesto de inversión | `constraints_b.py` |
| Variables, `W_EPS`, `capacity()` | — | `model.py` |

Cada restricción lleva en el código un comentario con su ecuación del informe (Sección 2).

## 6. Experimentos

| Script | Qué estudia | Salida en `results/experiments/` |
|---|---|---|
| `climate_runs.py --mode operation` | escenarios climáticos (qué limita: agua o frío) | `climate_operation.csv` |
| `water_pareto.py` | concesión, caudal y frontera beneficio–agua (ε-restricción con `W_EPS`) | `water_concession.csv`, `water_flow.csv`, `water_pareto.csv` |
| `sensitivity_physics.py` | validación y sensibilidad a pérdidas, umbrales y supuestos físicos | `sensitivity_physics.csv`, `validation.csv` |
| `climate_runs.py --mode investment` | escenarios climáticos con inversión | `climate_investment.csv` |
| `budget_sweep.py` | barrido del presupuesto de inversión | `budget_sweep.csv`, `budget_sweep_detalle.csv` |
| `aw_price_breakeven.py` | precio del *all-weather* (normal, +1 °C y +2 °C) | `aw_price_breakeven.csv` |
| `electricity_shock.py` | sensibilidad económica: electricidad +30 %, θ y M_KM | `economic_sensitivity.csv` |

Todos los scripts están en `src/experiments/` (con funciones comunes en `common.py`) y aceptan
`--solver`, `--gap`, `--time-limit` y `--relax-x`.

## 7. Decisiones de modelado relevantes para reproducir

- **x continua en los análisis (`--relax-x`).** El número de equipos en marcha es entero en el
  caso base de operación; en los análisis se relaja a continuo, manteniendo enteras las
  decisiones de apertura e inversión. La diferencia en el beneficio es del 0,7 % y la
  resolución es unas 9 veces más rápida (`results/normal_operation` frente a
  `results/normal_operation_relax`).
- **Gap de optimalidad del 1 %** por defecto.
- **beneficio_real** = ingresos − electricidad − inversión imputada, *sin* la penalización de
  los días clave. Es el que se usa en las tablas y figuras; el objetivo sí incluye la
  penalización.
- **R4 es blanda** (holgura penalizada con M_KM) para que el modelo sea siempre factible, y
  **R5 es una desigualdad** porque la captación del río es un máximo.
- **Parámetros económicos** en `data/processed/economics.yaml`: M_KM = 5.000 € por km
  incumplido en un día clave, presupuesto PSI = 3 M€ (coste total, sin anualizar), tasa de
  descuento r = 5 % y θ = 0,23 (fracción de la temporada que cae en el horizonte, para imputar
  la inversión). Costes y vida útil de los equipos en `data/processed/tech.csv`; costes de
  habilitar las posiciones en `data/processed/positions.csv`.
- **Parámetros de agua y energía** en `data/processed/water_energy.yaml`.

## 8. Estructura del repositorio

```
data/raw/           datos descargados (clima ERA5, OMIE) y plano de pistas de Cetursa
data/interim/       datos intermedios (bloques meteorológicos, calendario, precios horarios)
data/processed/     entradas del modelo (CSV/YAML) y escenarios climáticos
src/                código del modelo y del preprocesado
src/experiments/    análisis de sensibilidad y escenarios
results/            resultados de la ejecución del 22/11/2026 (casos, experimentos y figuras)
informe.pdf         informe del proyecto
run_all.py          reproduce todo
requirements.txt    dependencias de Python
```

## 9. Uso de inteligencia artificial

Se ha utilizado el asistente Claude (Anthropic) como apoyo en el proyecto; el detalle está en
la sección "Uso de herramientas de inteligencia artificial" del informe.
