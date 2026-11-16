"""
tarea B9. Carga los datos y devuelve el diccionario 'data' que usa model.py

Al final comprueba que los datos son coherentes (validate) y para si no lo son.
Uso directo:  python src/load_data.py --scenario normal   (solo carga y valida)
"""

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
INTERIM = ROOT / "data" / "interim"

K = ["FAN", "AW"]
M_KM_PROVISIONAL = 15000.0          # €/km incumplido, hasta tener economics.yaml (B6)

def read_yaml_simple(path: Path) -> dict:
    """Lee un yaml plano 'clave: valor #comentario, sin depender de pyymal"""
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#")[0].strip()
        if line:
            k,v = line.split(":", 1)
            out[k.strip()] = float(v)
    return out


def crf(r: float, n: float) -> float:
    """Factor de recuperación de capital: anualidad por euro invertido (vida n, tasa r)."""
    return r* (1+r) **n / ((1+r)**n-1)

def load_data(scenario: str= "normal") -> dict:
    scen = PROC /"scenarios" / scenario
    periods = pd.read_csv(INTERIM / "periods.csv")
    prod = pd.read_csv(scen / "production.csv")
    snow = pd.read_csv(scen / "snow.csv").fillna({"Z": 0.0})
    we = read_yaml_simple(PROC / "water_energy.yaml")
    inflow = pd.read_csv(PROC / "inflow.csv")

    pistas = pd.read_csv(PROC / "pistas.csv")
    pos = pd.read_csv(PROC/ "positions.csv")
    acc = pd.read_csv(PROC/ "access.csv")
    rev = pd.read_csv(PROC/ "revenue.csv")
    keyd = pd.read_csv(PROC/ "keydays.csv")
    prices = pd.read_csv(PROC/ "prices.csv")
    cand = pos[pos["type"] == "N"]

    data = {
        #conjuntos/sets
        "P": pistas["p"].tolist(),
        "J": pos["j"].tolist(),
        "JE": pos.loc[pos["type"] == "E", "j"].tolist(),
        "JN": cand["j"].tolist(),
        "K": K,
        "D": sorted(periods["d"].unique().tolist()),
        "T": periods["t"].tolist(),
        "DC": keyd["d"].tolist(),
        "Td": periods.groupby("d")["t"].apply(list).to_dict(),
        "Jp": pos.groupby("p")["j"].apply(list).to_dict(),
        "ACC": list(zip(acc["p"], acc["a"])),
        #persona A:Jimena
        "G": {(r.j, r.k, r.t): r.G for r in prod.itertuples()},
        "A": {(r.j, r.k, r.t): r.A for r in prod.itertuples()},
        "E": {(r.j, r.k, r.t): r.E for r in prod.itertuples()},
        "PHI": {"FAN": we["PHI_FAN"], "AW": we["PHI_AW"]},
        "DELTA": {(r.p, r.d): r.Delta for r in snow.itertuples()},
        "Z": {(r.p, r.d): r.Z for r in snow.itertuples()},
        "S0": dict(zip(pistas["p"], pistas["S0"].fillna(0.0))),
        "B_MAX": we["B_MAX"], "B0": we["B0"], "W": we["W"],
        "Q_MAX": we["Q_MAX"], "E_MAX": we["E_MAX"],
        "I": dict(zip(inflow["d"], inflow["I"])),
        #persona B: Adriana
        "PI": dict(zip(prices["t"], prices["Pi"])),
        "R": {(r.p, r.d): r.R for r in rev.itertuples()},
        "V": dict(zip(pistas["p"], pistas["V"])),
        "LEN": dict(zip(pistas["p"], pistas["length_km"])),
        "L": dict(zip(keyd["d"], keyd["L"])),
        "N0": {**{(r.j, "FAN"): int(r.N0_FAN) for r in pos.itertuples()},
               **{(r.j, "AW"): int(r.N0_AW) for r in pos.itertuples()}},
        "U": dict(zip(cand["j"], cand["U"])),
    }

    #economía de la inversión
    eco_path, tech_path = PROC / "economics.yaml", PROC /"tech.csv"
    if eco_path.exists() and tech_path.exists() and cand["F"].notna().all():
        eco = read_yaml_simple(eco_path)
        tech = pd.read_csv(tech_path).set_index("k")
        data["M_KM"] = eco["M_KM"]
        data["PSI"] = eco["PSI"]
        data["F"] = dict(zip(cand["j"], cand["F"]))
        data["C"] = tech["C"].to_dict()
        # Costes anualizados e imputados al horizonte: x CRF x theta
        crf_pos = crf(eco["r"], eco["life_positions"])
        data["FA"] = {j: F * crf_pos * eco["theta"] for j, F in data["F"].items()}
        data["CA"] = {k: tech.loc[k, "C"] * crf(eco["r"], tech.loc[k, "life_years"]) * eco["theta"]
                      for k in K}
    else:
        print(f"AVISO load_data: sin costes de inversión (B6) -> M_KM provisional = "
              f"{M_KM_PROVISIONAL:,.0f} €/km; el modo investment aún no es válido")
        data["M_KM"] = M_KM_PROVISIONAL

    validate(data)
    return data


def validate(data: dict) -> None:
    """Comprobaciones de coherencia entre ficheros. Para con un error si algo falla"""
    errors = []
    P, J, D, T = set(data["P"]), set(data["J"]), set(data["D"]), set(data["T"])

    #cada pos alimenta un único sector que existe
    for p, js in data["Jp"].items():
        if p not in P:
            errors.append(f"posiciones {js} apuntan al sector inexistente {p}")
    if len(J) != len(data["J"]):
        errors.append("hay posiciones repetidas en positions.csv")

    # Conexiones: sectores existentes, un solo acceso por sector y sin ciclos
    parent = {}
    for p, a in data["ACC"]:
        if p not in P or a not in P:
            errors.append(f"access.csv: conexión ({p}, {a}) con un sector inexistente")
        if p in parent:
            errors.append(f"access.csv: {p} tiene más de un acceso")
        parent[p] = a
    for p in P:
        seen, x = set(), p
        while x in parent:
            if x in seen:
                errors.append(f"access.csv: ciclo que pasa por {p}")
                break
            seen.add(x)
            x = parent[x]

    #cobertura de los datos indexados
    if set(data["PI"]) != T:
        errors.append("prices.csv no tiene exactamente un precio por bloque t")
    if set(data["R"]) != {(p, d) for p in P for d in D}:
        errors.append("revenue.csv no cubre todos los pares (p, d)")
    if not set(data["DC"]) <= D:
        errors.append("keydays.csv tiene días fuera del horizonte")
    if set(data["DELTA"]) != {(p, d) for p in P for d in D}:
        errors.append("snow.csv no cubre todos los pares (p, d)")
    if set(data["G"]) != {(j, k, t) for j in J for k in data["K"] for t in T}:
        errors.append("production.csv no cubre todos los (j, k, t)")

    #unidades / signos razonables 
    if any(v <= 0 for v in data["V"].values()):
        errors.append("pistas.csv: V debe ser > 0")
    if any(v < 0 for v in data["PI"].values()):
        print("AVISO load_data: hay precios de la luz negativos (posible en OMIE)")

    if errors:
        raise ValueError("Datos incoherentes:\n  - " + "\n  - ".join(errors))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="normal")
    args = ap.parse_args()
    d = load_data(args.scenario)
    print(f"OK escenario {args.scenario}: {len(d['P'])} sectores, {len(d['J'])} posiciones "
          f"({len(d['JN'])} candidatas), {len(d['D'])} días, {len(d['T'])} bloques, "
          f"{len(d['DC'])} días clave")
