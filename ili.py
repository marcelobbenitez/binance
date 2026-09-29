"""Índice de Liquidez Institucional (ILI): versión simplificada.

El ILI original (según el resumen del proyecto) combina flujos de ETF con
"liquidez USD" agregada (algo tipo balance de la Fed / M2), pero esa segunda
mitad no tiene una fuente gratuita y en tiempo real, así que esta versión usa
solo la mitad que sí podemos calcular con datos propios: el flujo neto de ETF
normalizado contra su propio rango histórico (Average/Maximum/Minimum diarios
que Farside publica para cada activo). Queda documentado como una
simplificación deliberada, no como el ILI completo del resumen original.

Score 0-100: 0 = el peor outflow diario histórico, 100 = el mejor inflow
diario histórico, 50 = en línea con el promedio histórico.
"""


def compute_score(flujo_neto_usd_m, dias_con_dato, stats):
    """`stats` es el dict de etf_flows.get_flow_stats() ({'average',
    'maximum', 'minimum'} del flujo diario total histórico, en USD millones).
    Devuelve None si falta algún dato (activo sin ETF, sin histórico, etc.)."""
    if flujo_neto_usd_m is None or not dias_con_dato or not stats:
        return None

    lo, hi = stats.get("minimum"), stats.get("maximum")
    if lo is None or hi is None or hi <= lo:
        return None

    promedio_diario = flujo_neto_usd_m / dias_con_dato
    score = (promedio_diario - lo) / (hi - lo) * 100
    return max(0.0, min(100.0, score))


def es_maximo_de_n_dias(precio_actual, velas, dias=30):
    """True si `precio_actual` iguala o supera el máximo ('high') de las
    últimas `dias` velas diarias. Devuelve None si no hay velas suficientes."""
    if not velas:
        return None
    recientes = velas[-dias:]
    if not recientes:
        return None
    maximo = max(v["high"] for v in recientes)
    return precio_actual >= maximo
