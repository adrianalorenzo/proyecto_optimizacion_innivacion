"""
constraints_a.py  —  Persona A, tarea A7: restricciones físicas y de recursos.

R1  Solo funcionan equipos instalados y en bloques aptos
        x_{j,k,t} <= A_{j,k,t} (N0_{j,k} + n_{j,k})                 ∀ j,k,t
R2  Balance de nieve de cada sector
        s_{p,d} = (1 - DELTA_{p,d}) s_{p,d-1} + Z_{p,d}
                  + Σ_{j∈J(p),k} Σ_{t∈T(d)} G_{j,k,t} x_{j,k,t}       ∀ p,d
        con s_{p,-1} = S0_p
R5  Balance de la balsa (la cota superior B_MAX va en la variable b)
        b_d = b_{d-1} + I_d - Σ_k PHI_k Σ_j Σ_{t∈T(d)} G_{j,k,t} x_{j,k,t}   ∀ d
        con b_{-1} = B0
R6  Concesión de agua del horizonte / límite ε
        Σ_{j,k,t} PHI_k G_{j,k,t} x_{j,k,t} <= W_EPS
R7  Energía y caudal máximos por bloque
        Σ_{j,k} E_{j,k,t} x_{j,k,t} <= E_MAX                         ∀ t
        Σ_{j,k} PHI_k G_{j,k,t} x_{j,k,t} <= Q_MAX                   ∀ t
"""

import pyomo.environ as pyo


def add_constraints_a(m, data: dict) -> None:
    from model import capacity

    G, A, E, PHI = data["G"], data["A"], data["E"], data["PHI"]
    Td, Jp = data["Td"], data["Jp"]
    D = list(m.D)

    def water(j, k, t):
        """Agua (m³) que gasta un equipo en un bloque."""
        return PHI[k] * G[j, k, t]

    # R1 -------------------------------------------------------------------
    def r1(m, j, k, t):
        if A[j, k, t] == 0:                       # bloque no apto: no funciona
            return m.x[j, k, t] == 0
        return m.x[j, k, t] <= capacity(m, j, k)
    m.R1 = pyo.Constraint(m.J, m.K, m.T, rule=r1)

    # R2 -------------------------------------------------------------------
    def r2(m, p, d):
        i = D.index(d)
        prev = data["S0"][p] if i == 0 else m.s[p, D[i - 1]]
        produced = sum(G[j, k, t] * m.x[j, k, t]
                       for j in Jp.get(p, []) for k in m.K for t in Td[d])
        return m.s[p, d] == (1 - data["DELTA"][p, d]) * prev + data["Z"][p, d] + produced
    m.R2 = pyo.Constraint(m.P, m.D, rule=r2)

    # R5 -------------------------------------------------------------------
    def r5(m, d):
        i = D.index(d)
        prev = data["B0"] if i == 0 else m.b[D[i - 1]]
        used = sum(water(j, k, t) * m.x[j, k, t]
                   for j in m.J for k in m.K for t in Td[d])
        return m.b[d] == prev + data["I"][d] - used
    m.R5 = pyo.Constraint(m.D, rule=r5)

    # R6 -------------------------------------------------------------------
    m.R6 = pyo.Constraint(expr=sum(water(j, k, t) * m.x[j, k, t]
                                   for j in m.J for k in m.K for t in m.T) <= m.W_EPS)

    # R7 -------------------------------------------------------------------
    m.R7_energy = pyo.Constraint(m.T, rule=lambda m, t: sum(
        E[j, k, t] * m.x[j, k, t] for j in m.J for k in m.K) <= data["E_MAX"])
    m.R7_flow = pyo.Constraint(m.T, rule=lambda m, t: sum(
        water(j, k, t) * m.x[j, k, t] for j in m.J for k in m.K) <= data["Q_MAX"])
