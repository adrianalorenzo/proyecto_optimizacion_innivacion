"""
sensitivity_physics.py  —  Persona A, análisis S-A3: validación y sensibilidad
a los supuestos físicos.

Se cambia UN supuesto cada vez (el resto en su valor base), se regeneran en
memoria los datos que dependen de él y se vuelve a resolver:

  supuesto            valores            afecta a     dónde está
  DDF (grado-día)     2, 4*, 6           DELTA        snow_physics.DDF
  SUBL (evaposubl.)   0, 1*, 2 mm/día    DELTA        snow_physics.SUBL
  H_REF (manto ref.)  0,3 0,5* 0,8 m     DELTA        snow_physics.H_REF
  percentil viento    0,75 0,85* 0,95    A, G, E      process_weather.WIND_PERCENTILE
  horas aptas/bloque  1, 2*, 3           A, G, E      process_weather.MIN_APT_HOURS
  rendimiento FAN     x0,8 x1* x1,2      G, E (FAN)   curva de snowmaking.py
  (* = valor base)

Validación (validation.csv):
  - sin agua (W ≈ 0) no se produce nieve,
  - con +20 °C solo produce el all-weather (con +10 °C aún hay horas a -6 °C a 3150 m),
  - la producción se concentra de noche (frío + luz barata).

Salida: results/experiments/sensitivity_physics.csv y validation.csv
Uso:    python src/experiments/sensitivity_physics.py --scenario normal
"""

import argparse

import pandas as pd

from common import quiet_load, regen_production, regen_snow, save_table  # añade src/ al path
import process_weather as pw
import snow_physics as sp
from solve import kpis, prepare, run_solver, water_used

SNOW_CASES = [("DDF (mm/°C·día)", "DDF", [2.0, 4.0, 6.0]),
              ("Evaposublimación (mm/día)", "SUBL", [0.0, 1.0, 2.0]),
              ("Manto de referencia (m)", "H_REF", [0.3, 0.5, 0.8])]
PRODUCTION_CASES = [("Percentil de viento", "WIND_PERCENTILE", [0.75, 0.85, 0.95]),
                    ("Horas aptas mínimas por bloque", "MIN_APT_HOURS", [1, 2, 3])]
FAN_FACTORS = [0.8, 1.0, 1.2]


def snow_data(base, sc, attr, value):
    """DELTA y Z recalculados con snow_physics.<attr> = value (y se restaura)."""
    old = getattr(sp, attr)
    setattr(sp, attr, value)
    sp.SWE_REF = sp.H_REF * sp.RHO_GROOMED * 1000          # depende de H_REF
    data = regen_snow(base, sc)
    setattr(sp, attr, old)
    sp.SWE_REF = sp.H_REF * sp.RHO_GROOMED * 1000
    return data


def production_data(base, sc, attr, value):
    """G, A, E recalculados con process_weather.<attr> = value (y se restaura)."""
    old = getattr(pw, attr)
    setattr(pw, attr, value)
    data = regen_production(base, sc)
    setattr(pw, attr, old)
    return data


def scale_fan(data, f):
    """Ventilador que produce f veces la curva base (la energía escala igual)."""
    G = {key: g * f if key[1] == "FAN" else g for key, g in data["G"].items()}
    E = {key: e * f if key[1] == "FAN" else e for key, e in data["E"].items()}
    return dict(data, G=G, E=E)


def solve(data, args):
    m = prepare(data, "operation", quiet=True)
    status, gap, secs, _ = run_solver(m, args.solver, args.gap, args.time_limit, quiet=True)
    out = {"estado": status, "gap": gap, "t_s": round(secs, 1)}
    if status != "sin_solucion":
        out.update(kpis(m, data))
    return out, m


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="normal")
    ap.add_argument("--solver", default=None)
    ap.add_argument("--gap", type=float, default=0.01)
    ap.add_argument("--time-limit", type=int, default=300)
    args = ap.parse_args()
    sc = args.scenario
    base = quiet_load(sc)

    # (nombre, valor, datos) para cada caso
    cases = []
    for name, attr, values in SNOW_CASES:
        cases += [(name, v, snow_data(base, sc, attr, v)) for v in values]
    for name, attr, values in PRODUCTION_CASES:
        cases += [(name, v, production_data(base, sc, attr, v)) for v in values]
    cases += [("Rendimiento ventilador (x)", f, scale_fan(base, f)) for f in FAN_FACTORS]

    rows = []
    for name, value, data in cases:
        res, _ = solve(data, args)
        rows.append({"supuesto": name, "valor": value, **res})
        print(f"  {name:32s} {value:>5}  obj={res.get('objetivo')}  agua={res.get('agua_usada_m3')}")
    table = pd.DataFrame(rows)
    base_obj, _ = solve(base, args)
    table["var_obj_pct"] = (100 * (table["objetivo"] / base_obj["objetivo"] - 1)).round(1)
    save_table(table, "sensitivity_physics")

    # ------------------------------ Validación ------------------------------
    print("Validación")
    val = []
    res, _ = solve(dict(base, W=1e-6), args)
    produced = res.get("nieve_producida_m3") or 0
    val.append({"prueba": "Sin agua (W ≈ 0) no se produce nieve",
                "resultado": produced, "ok": produced < 1})

    hot = regen_production(base, sc, extra_dT=20.0)
    _, m = solve(hot, args)
    fan = sum(hot["G"][j, "FAN", t] * (m.x[j, "FAN", t].value or 0) for j in m.J for t in m.T)
    val.append({"prueba": "Con +20 °C solo produce el all-weather (m³ de ventilador)",
                "resultado": round(fan, 1), "ok": fan < 1})

    _, m = solve(base, args)
    hours = pd.read_csv(pw.OUT_DIR / "periods.csv").set_index("t")["hour_start"]
    by_hour = pd.Series({t: water_used(m, base, t) for t in m.T}).groupby(hours).sum()
    night = by_hour.loc[[0, 3, 21]].sum() / by_hour.sum()
    val.append({"prueba": "% del agua usado de 21 h a 6 h (3 de 8 bloques -> 37,5 % si fuera uniforme)",
                "resultado": round(100 * night, 1), "ok": night > 0.375})
    for v in val:
        print(f"  {'OK' if v['ok'] else 'NO'}  {v['prueba']}: {v['resultado']}")
    path = save_table(pd.DataFrame(val), "validation")
    print(f"Listo. Tablas en {path.parent}")


if __name__ == "__main__":
    main()
