"""
model.py  —  Esqueleto COMÚN del MILP (Persona A + Persona B).

Aquí solo hay conjuntos y variables (sección 3 del plan). Las restricciones y
la función objetivo están en dos ficheros, para que cada una edite el suyo
sin pisarse en git:
    constraints_a.py  (Persona A)  R1, R2, R5, R6, R7
    constraints_b.py  (Persona B)  función objetivo, R3, R4, R8, R9

Notación: parámetros en MAYÚSCULAS, variables en minúsculas (igual que el
informe). Los parámetros se leen directamente del diccionario `data`.

Diccionario `data` (lo construye load_data.py, tarea B9). Claves:
  Conjuntos:   P, J, JE, JN, K, D, DC, T,
               Td  {d: [t...]}  bloques de cada día
               Jp  {p: [j...]}  posiciones de cada sector
               ACC [(p, a)...]  conexiones: p necesita a abierta
  Persona A:   G, A, E  {(j,k,t)},  PHI {k},  DELTA, Z {(p,d)},  S0 {p},
               B_MAX, B0, W, Q_MAX, E_MAX (escalares),  I {d}
  Persona B:   PI {t}, R {(p,d)}, V {p}, LEN {p}, L {d}, M_KM,
               N0 {(j,k)}, U {j}, F {j}, C {k}, FA {j}, CA {k}, PSI
"""

import pyomo.environ as pyo

from constraints_a import add_constraints_a

try:                                    # lo escribe la Persona B
    from constraints_b import add_constraints_b
except ImportError:
    add_constraints_b = None


B_KEYS = ("PI", "R", "LEN", "L", "ACC", "M_KM")      # datos mínimos de la parte de B


def build_model(data: dict, mode: str = "investment", eps: float | None = None,
                include_b: bool | None = None):
    """Construye el MILP.
    mode = "operation"  -> apartado (a): sin inversión (u = 0, n = 0)
           "investment" -> apartado (b): inversión + operación
    eps  = límite de agua del método ε-restricción (None = solo la concesión W)
    include_b = añadir la parte de B (objetivo, R3, R4, R8, R9). Por defecto,
           sí cuando existe constraints_b.py y `data` trae sus datos (B_KEYS);
           si no, el modelo queda sin objetivo (lo pone quien lo llama).
    """
    if include_b is None:
        include_b = add_constraints_b is not None and all(k in data for k in B_KEYS)
    m = pyo.ConcreteModel(name="Innivacion Sierra Nevada")
    m.data = data

    # ---------------- Conjuntos ----------------
    m.P = pyo.Set(initialize=data["P"])
    m.J = pyo.Set(initialize=data["J"])
    m.JE = pyo.Set(within=m.J, initialize=data["JE"])
    m.JN = pyo.Set(within=m.J, initialize=data["JN"])
    m.K = pyo.Set(initialize=data["K"])
    m.D = pyo.Set(initialize=data["D"], ordered=True)
    m.DC = pyo.Set(within=m.D, initialize=data["DC"])
    m.T = pyo.Set(initialize=data["T"], ordered=True)

    # ---------------- Variables ----------------
    m.x = pyo.Var(m.J, m.K, m.T, domain=pyo.NonNegativeIntegers)   # equipos en marcha
    m.y = pyo.Var(m.P, m.D, domain=pyo.Binary)                     # pista abierta
    m.s = pyo.Var(m.P, m.D, domain=pyo.NonNegativeReals)           # nieve al final del día
    m.b = pyo.Var(m.D, domain=pyo.NonNegativeReals,
                  bounds=(0, data["B_MAX"]))                       # agua en la balsa
    m.u = pyo.Var(m.JN, domain=pyo.Binary)                         # habilitar candidata
    m.n = pyo.Var(m.JN, m.K, domain=pyo.NonNegativeIntegers)       # equipos nuevos
    m.h = pyo.Var(m.DC, domain=pyo.NonNegativeReals)               # km incumplidos

    # Límite de agua del ε-restricción: parámetro mutable para poder cambiarlo
    # sin reconstruir el modelo (frontera de Pareto, análisis S-A2)
    m.W_EPS = pyo.Param(mutable=True, initialize=data["W"] if eps is None else min(eps, data["W"]))

    # Modo (a): sin inversión
    if mode == "operation":
        for j in m.JN:
            m.u[j].fix(0)
            for k in m.K:
                m.n[j, k].fix(0)

    add_constraints_a(m, data)
    if include_b:
        add_constraints_b(m, data)
    return m


def capacity(m, j, k):
    """Equipos disponibles en j de tecnología k: existentes + nuevos."""
    cap = m.data["N0"].get((j, k), 0)
    if j in m.JN:
        cap = cap + m.n[j, k]
    return cap
