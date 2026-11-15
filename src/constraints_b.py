"""
constraints_b. 

Función objetivo (beneficio neto en el horizonte, euros):
 max  Σ_{p,d} R_{p,d} y_{p,d}                         ingresos por sectores abiertos
       - Σ_{j,k,t} PI_t E_{j,k,t} x_{j,k,t}              coste eléctrico
       - Σ_{j∈JN} FA_j u_j                               habilitar posiciones (anualizado)
       - Σ_{j∈JN,k} CA_k n_{j,k}                         equipos nuevos (anualizado)
       - Σ_{d∈DC} M_KM h_d                               km de compromiso incumplidos

R3a  Abrir exige nieve suficiente
        s_{p,d} >= V_p y_{p,d}                                    ∀ p,d
R3b  Abrir exige que el acceso esté abierto (red de pistas)
        y_{p,d} <= y_{a,d}                                        ∀ (p,a)∈ACC, d
R4   Km mínimos en días clave (compromiso comercial, blando)
        Σ_p LEN_p y_{p,d} + h_d >= L_d                            ∀ d∈DC
R8   Solo se instala en posiciones candidatas habilitadas
        Σ_k n_{j,k} <= U_j u_j                                    ∀ j∈JN
R9   Presupuesto de inversión (coste total, no anualizado)
        Σ_{j∈JN} F_j u_j + Σ_{j∈JN,k} C_k n_{j,k} <= PSI
"""

#seguimos usando pyomo al igual que en las prácticas

import pyomo.environ as pyo

def add_constraints_b(m, data: dict) -> None:
    PI, E, R = data["PI"], data["E"], data["R"]
    V, LEN, L = data["V"], data["LEN"], data["L"]
    M_KM = data["M_KM"]

    #costes de inversión (tarea B6). Si faltan: 0 y presupuesto ilimitadi
    investing = any(not m.u[j].fixed for j in m.JN)
    missing = [k for k in ("F", "C", "FA", "CA", "PSI", "U") if k not in data]
    if investing and missing:
        print(f"AVISO constraints_b: faltan costes de inversión {missing} -> se usan 0")

    F = data.get("F", {})
    C = data.get("C", {})
    FA = data.get("FA", {})
    CA = data.get("CA", {})
    U = data.get("U", {})
    PSI = data.get("PSI", float("inf"))

    #funcion objetivo
    revenue = sum(R[p,d] * m.y[p,d] for p in m.P for d in m.D)
    electricity = sum(PI[t] * E[j,k,t]*m.x[j,k,t]
                      for j in m.J for k in m.K for t in m.T)
    investment = (sum(FA.get(j, 0.0)*m.u[j] for j in m.JN) +sum(CA.get(k, 0.0)*m.n[j,k] for j in m.JN for k in m.K))
    penalty = sum(M_KM * m.h[d] for d in m.DC)

    #guardamos por separado apra poder informar de cada término después
    m.REVENUE = pyo.Expression(expr=revenue)
    m.ELECTRICITY = pyo.Expression(expr=electricity)
    m.INVESTMENT = pyo.Expression(expr=investment)
    m.PENALTY = pyo.Expression(expr=penalty)
    m.obj = pyo.Objective(expr=m.REVENUE - m.ELECTRICITY - m.INVESTMENT - m.PENALTY,
                          sense=pyo.maximize)

    #R3a
    m.R3a = pyo.Constraint(m.P, m.D, rule=lambda m, p, d: m.s[p, d] >= V[p] * m.y[p, d])

    #R3b
    acc = [(p, a) for (p, a) in data["ACC"] if p in m.P and a in m.P]
    m.ACC = pyo.Set(initialize=acc, dimen=2)
    m.R3b = pyo.Constraint(m.ACC, m.D, rule=lambda m, p, a, d: m.y[p, d] <= m.y[a, d])

    #R4
    m.R4 = pyo.Constraint(m.DC, rule=lambda m, d: sum(LEN[p] * m.y[p, d] for p in m.P) + m.h[d] >= L[d])

    #R8
    def r8(m, j):
        if j not in U:
            return pyo.Constraint.Skip
        return sum(m.n[j, k] for k in m.K) <= U[j] * m.u[j]
    m.R8 = pyo.Constraint(m.JN, rule=r8)

    #R9
    if PSI != float("inf"):
        m.R9 = pyo.Constraint(expr=sum(F.get(j, 0.0) * m.u[j] for j in m.JN)
                              + sum(C.get(k, 0.0) * m.n[j, k] for j in m.JN for k in m.K)
                              <= PSI)
