# Innivación artificial en Sierra Nevada — MILP

Proyecto final de **Optimización y Simulación** (GiMAT, Comillas ICAI).
Autoras: Jimena y Adriana.

Modelo de programación lineal entera mixta (Pyomo) que decide, en bloques de 3 horas
durante una temporada (424 bloques), **cuándo y con qué cañones producir nieve** en cada
sector de Sierra Nevada, respetando el agua (concesión y balsas), la potencia eléctrica y el
frío disponible, para maximizar el beneficio de la estación. Tiene dos modos:

- **(a) Operación:** el parque de cañones actual es fijo; solo se decide la producción.
- **(b) Inversión:** además se decide cuántos equipos nuevos de cada tecnología instalar y en qué posiciones, con presupuesto.

---

## 1. Instalación

```bash
pip install -r requirements.txt
```

- **Solver:** se usa **Gurobi** si está instalado (licencia académica); si no, **HiGHS**
  (`highspy`, incluido en `requirements.txt`). El orden de preferencia está en
  `src/test_model_a.py` (`pick_solver`). Se puede forzar con `--solver highs`.
- En Windows, si Pyomo no encuentra Gurobi, ejecutar con el Python que tiene `gurobipy`
  (en nuestro caso `py -3.13 ...`).
- No hace falta internet: los datos meteorológicos descargados (ERA5 vía Open-Meteo) y
  los precios OMIE ya están en `data/raw/`.

## 2. Reproducir todos los resultados

```bash
python run_all.py                 # todo: datos + casos base + experimentos + figuras
python run_all.py --skip-data     # sin regenerar datos (usa data/processed tal cual)
python run_all.py --only-plots    # solo rehace las figuras
```

**Tiempo de ejecución.** La ejecución completa resuelve el modelo unas 60 veces y
tarda varias horas. Tiempos orientativos con Gurobi en un portátil (19/11/2026, con el
ordenador ocupado en otras tareas, así que con el equipo libre debería ser menos):

| Paso | Resoluciones | Tiempo |
|---|---|---|
| Casos base (operación con x entera y continua, inversión) | 3 | 6 min |
| `climate_runs.py --mode operation` | 5 | 1,5 min |
| `water_pareto.py` | 15 | 4 min |
| `sensitivity_physics.py` (incluye la validación) | 21 | 8 min |
| `climate_runs.py --mode investment` | 5 | 29 min |
| `budget_sweep.py` | 9 | 35 min |
| `aw_price_breakeven.py` | 21 | 3 h 24 min |
| `electricity_shock.py` | 6 | 50 min |

Los experimentos usan `--relax-x` (ver §6). Cada resolución tiene un límite de tiempo
(`--time-limit`, 600 s por defecto); si se alcanza, se guarda la mejor solución
encontrada y su *gap* aparece en la columna `gap` de los CSV. Conviene ejecutar con el
ordenador enchufado y sin suspensión: Gurobi mide el tiempo real, y una suspensión a
mitad de una resolución la detiene por límite de tiempo.

Un caso suelto:

```bash
python src/solve.py --scenario normal --mode operation              # x entera
python src/solve.py --scenario normal --mode investment --relax-x   # x continua
# opciones: --days N (recortar horizonte), --gap 0.01, --time-limit 600, --solver gurobi|highs
```

Los resultados se guardan en `results/<escenario>_<modo>[_relax]/` (CSV por variable y
`summary.json` con los KPIs), los experimentos en `results/experiments/` y las figuras en
`results/figures/`. La carpeta `results/` no se sube a git: se regenera con `run_all.py`.

## 3. Flujo de datos

```
Clima, nieve y agua
  weather.py            ERA5 horario (Open-Meteo)              -> data/raw/weather/
  process_weather.py    cota, bulbo húmedo, viento, aptitud,
                        bloques de 3 h                         -> data/interim/weather_blocks.csv
  snowmaking.py         curvas de producción por tecnología,
                        kWh/m³, Φ_k  (lo importan los demás)
  snow_physics.py       pérdidas Δ (grado-día + evaposublimación), Z
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
  constraints_b.py      objetivo y restricciones de estación/inversión
  solve.py              resuelve un escenario y exporta resultados/KPIs
  plots.py              figuras del informe
```

## 4. Restricciones ↔ código

| Restricción | Qué representa | Dónde |
|---|---|---|
| Objetivo | ingresos − coste eléctrico − inversión − M_KM · km incumplidos en días clave | `constraints_b.py` |
| R1 | solo funcionan equipos instalados y en bloques aptos (x ≤ A·(N0 + n)) | `constraints_a.py` |
| R2 | balance de nieve acumulada de cada sector (pérdidas Δ, nieve natural Z, producción G·x) | `constraints_a.py` |
| R3a | abrir una pista exige nieve suficiente | `constraints_b.py` |
| R3b | abrir exige que el acceso esté abierto (red de pistas) | `constraints_b.py` |
| R4 | km mínimos abiertos en días clave (blanda, holgura h_d) | `constraints_b.py` |
| R5 | balance de la balsa (captación ≤ I_d; B_MAX como cota de b) | `constraints_a.py` |
| R6 | concesión de agua de la temporada / límite ε (`W_EPS`) | `constraints_a.py` |
| R7 | energía (E_MAX) y caudal (Q_MAX) máximos por bloque | `constraints_a.py` |
| R8 | solo se instala en posiciones candidatas habilitadas | `constraints_b.py` |
| R9 | presupuesto de inversión | `constraints_b.py` |
| Variables, `W_EPS`, `capacity()` | — | `model.py` |

En el modo operación las variables de inversión `u` y `n` se fijan a 0.

## 5. Experimentos

| Script | Qué estudia | Salida en `results/experiments/` |
|---|---|---|
| `climate_runs.py --mode operation` | escenarios climáticos (qué limita: agua o frío) | `climate_operation.csv` |
| `water_pareto.py` | concesión, caudal y frontera beneficio–agua (ε-restricción con `W_EPS`) | `water_pareto.csv`, `water_concession.csv`, `water_flow.csv` |
| `sensitivity_physics.py` | validación y sensibilidad a pérdidas, umbrales y supuestos físicos | `sensitivity_physics.csv`, `validation.csv` |
| `budget_sweep.py` | barrido de presupuesto de inversión | `budget_sweep.csv`, `budget_sweep_detalle.csv` |
| `aw_price_breakeven.py` | precio de equilibrio de la tecnología AW | `aw_price_breakeven.csv` |
| `climate_runs.py --mode investment` | escenarios climáticos con inversión | `climate_investment.csv` |
| `electricity_shock.py` | sensibilidad económica: electricidad +30 %, θ y M_KM | `economic_sensitivity.csv` |

Todos los scripts están en `src/experiments/` y aceptan `--solver`, `--gap`, `--time-limit`
y `--relax-x`.

## 6. Decisiones de modelado relevantes para reproducir

- **x continua en los análisis (`--relax-x`).** El número de cañones encendidos es entero
  en el caso base; en los barridos se relaja a continuo. Diferencia en el objetivo < 1 %
  y unas 9 veces más rápido (comparación en `results/normal_operation` frente a
  `results/normal_operation_relax`).
- **Gap de optimalidad del 1 %** por defecto.
- **beneficio_real** = ingresos − electricidad − inversión, *sin* la penalización de días
  clave; es el que se usa en tablas y figuras (el objetivo incluye la penalización).
- **Parámetros económicos** en `data/processed/economics.yaml`: penalización
  M_KM = 5.000 € por km incumplido en un día clave, presupuesto PSI = 3 M€ (coste total),
  tasa de descuento r = 5 % y θ = 0,23 (fracción de la temporada que cae en el horizonte,
  para imputar la inversión). Costes de los equipos y vida útil en `data/processed/tech.csv`.

## 7. Estructura del repositorio

```
data/raw/         datos descargados (clima, OMIE)
data/interim/     datos intermedios (bloques meteorológicos, calendario, precios horarios)
data/processed/   entradas del modelo (CSV/YAML) y escenarios climáticos
src/              código del modelo y del preprocesado
src/experiments/  análisis de sensibilidad y escenarios
results/          salidas (no versionado)
run_all.py        reproduce todo
```