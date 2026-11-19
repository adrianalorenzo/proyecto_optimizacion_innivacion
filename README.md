# Innivación artificial en Sierra Nevada — MILP

Proyecto final de **Optimización y Simulación** (GiMAT, Comillas ICAI).
Autoras: Jimena (Persona A: clima, nieve y agua) y Adriana (Persona B: estación, economía e inversión).

Modelo de programación lineal entera mixta (Pyomo) que decide, en bloques de 3 horas
durante una temporada (424 bloques), **cuándo y con qué cañones producir nieve** en cada
pista de Sierra Nevada, respetando el agua (concesión y balsas), la potencia eléctrica y el
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

Tiempo aproximado con Gurobi: la ejecución completa tarda del orden de una hora
(los experimentos usan `--relax-x`, ver §6).

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
Persona A (clima, nieve y agua)
  weather.py            ERA5 horario (Open-Meteo)              -> data/raw/weather/
  process_weather.py    cota, bulbo húmedo, viento, aptitud,
                        bloques de 3 h                         -> data/interim/weather_blocks.csv
  snowmaking.py         curvas de producción por tecnología,
                        kWh/m³, Φ_k  (lo importan los demás)
  snow_physics.py       pérdidas Δ (grado-día + evaposublimación), Z
  climate_scenarios.py  temporadas fría / normal / cálida, +1 °C, +2 °C (delta change)
                                                               -> data/processed/scenarios/
  water.py              concesión, balsas, Q_MAX, entrada diaria -> water_energy.yaml, inflow.csv

Persona B (estación, economía e inversión)
  economics.py          pistas, posiciones, tecnologías, ingresos, días clave
                                                               -> pistas.csv, positions.csv, tech.csv,
                                                                  revenue.csv, keydays.csv, economics.yaml
  prices.py             precio horario OMIE -> precio por bloque -> prices.csv

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

| Id | Script | Qué estudia | Salida en `results/experiments/` |
|---|---|---|---|
| S-A1 | `climate_runs.py --mode operation` | escenarios climáticos (qué limita: agua o frío) | `climate_operation.csv` |
| S-A2 | `water_pareto.py` | frontera beneficio–agua (ε-restricción con `W_EPS`) | `water_pareto.csv`, `water_concession.csv`, `water_flow.csv` |
| S-A3 | `sensitivity_physics.py` | sensibilidad a pérdidas, umbrales y supuestos físicos | `sensitivity_physics.csv`, `validation.csv` |
| S-B1 | `budget_sweep.py` | barrido de presupuesto de inversión | `budget_sweep.csv`, `budget_sweep_detalle.csv` |
| S-B2 | `aw_price_breakeven.py` | precio de equilibrio de la tecnología AW | `aw_price_breakeven.csv` |
| — | `climate_runs.py --mode investment` | escenarios climáticos con inversión | `climate_investment.csv` |

Todos los scripts están en `src/experiments/` y aceptan `--solver`, `--gap`, `--time-limit`
y `--relax-x`.

## 6. Decisiones de modelado relevantes para reproducir

- **x continua en los análisis (`--relax-x`).** El número de cañones encendidos es entero
  en el caso base; en los barridos se relaja a continuo. Diferencia en el objetivo < 1 %
  y unas 5 veces más rápido (comparación en `results/normal_operation` frente a
  `results/normal_operation_relax`).
- **Gap de optimalidad del 1 %** por defecto.
- **beneficio_real** = ingresos − electricidad − inversión, *sin* la penalización de días
  clave; es el que se usa en tablas y figuras (el objetivo incluye la penalización).
- **M_KM = 5.000 € por km incumplido en un día clave**, en `data/processed/economics.yaml`.

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

## 8. Reparto

- **Persona A (Jimena):** `weather.py`, `process_weather.py`, `snowmaking.py`,
  `snow_physics.py`, `climate_scenarios.py`, `water.py`, `model.py`, `constraints_a.py`,
  `solve.py`, `plots.py`, `run_all.py`, experimentos S-A1 a S-A3.
- **Persona B (Adriana):** `economics.py`, `prices.py`, `load_data.py`,
  `constraints_b.py`, experimentos S-B1 y S-B2.
