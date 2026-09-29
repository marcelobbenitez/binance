"""Cruce de señales para estimar sesgo alcista/bajista de un activo.

Sirve tanto para BTC como para ETH o BNB: no se usa una sola métrica, se
cruzan precio spot, flujo neto de ETF (7 días, cuando el activo tiene ETF
spot), funding rate de futuros perpetuos, el Índice de Liquidez
Institucional (ILI, ver ili.py) y el flujo neto a exchanges (CryptoQuant,
ver exchange_netflow.py; requiere API key propia, opcional).
"""

FUNDING_OVERHEATED_PCT = 0.05   # funding > esto: posicionamiento largo excesivo
FUNDING_HEALTHY_MIN_PCT = 0.0   # funding en [0, OVERHEATED]: alcista sano
ILI_FUERTE = 60
ILI_DEBIL = 40


def _signal_precio(cambio_24h_pct):
    if cambio_24h_pct > 0:
        return "alcista", f"Precio +{cambio_24h_pct:.2f}% en 24h"
    if cambio_24h_pct < 0:
        return "bajista", f"Precio {cambio_24h_pct:.2f}% en 24h"
    return "neutral", "Precio plano en 24h"


def _signal_etf(flujo_neto_7d_usd_m):
    if flujo_neto_7d_usd_m is None:
        return "sin_datos", "Sin datos de flujo ETF"
    if flujo_neto_7d_usd_m > 0:
        return "alcista", f"Inflow neto ETF de ${flujo_neto_7d_usd_m:,.1f}M en 7 días"
    if flujo_neto_7d_usd_m < 0:
        return "bajista", f"Outflow neto ETF de ${flujo_neto_7d_usd_m:,.1f}M en 7 días"
    return "neutral", "Flujo ETF neto plano en 7 días"


def _signal_funding(funding_pct):
    if funding_pct is None:
        return "sin_datos", "Sin datos de funding rate"
    if funding_pct < 0:
        return "bajista", f"Funding negativo ({funding_pct:.4f}%) — presión vendedora / deleveraging"
    if funding_pct > FUNDING_OVERHEATED_PCT:
        return "cautela", f"Funding muy alto ({funding_pct:.4f}%) — posible sobrecalentamiento"
    return "alcista", f"Funding positivo y sano ({funding_pct:.4f}%)"


def _signal_ili(ili_score):
    if ili_score is None:
        return "sin_datos", "Sin datos de ILI (requiere flujo ETF)"
    if ili_score >= ILI_FUERTE:
        return "alcista", f"ILI en {ili_score:.0f}/100 — liquidez institucional fuerte"
    if ili_score <= ILI_DEBIL:
        return "bajista", f"ILI en {ili_score:.0f}/100 — liquidez institucional débil"
    return "neutral", f"ILI en {ili_score:.0f}/100 — liquidez institucional moderada"


def _signal_exchange_netflow(netflow_neto, unidad):
    if netflow_neto is None:
        return "sin_datos", "Sin datos de flujo a exchanges (requiere CRYPTOQUANT_API_KEY)"
    if netflow_neto < 0:
        return "alcista", f"Salida neta de {abs(netflow_neto):,.0f} {unidad} de exchanges en 7 días"
    if netflow_neto > 0:
        return "bajista", f"Entrada neta de {netflow_neto:,.0f} {unidad} a exchanges en 7 días"
    return "neutral", "Flujo neto a exchanges plano en 7 días"


def _divergencia_precio_etf(sig_precio, sig_etf):
    if sig_precio == "alcista" and sig_etf == "bajista":
        return {
            "tipo": "DIVERGENCIA_AMARILLA",
            "nota": "Precio sube pero las instituciones retiran capital vía ETF — señal de cautela",
        }
    if sig_precio == "bajista" and sig_etf == "alcista":
        return {
            "tipo": "DIVERGENCIA_VERDE",
            "nota": "Precio baja pero las instituciones acumulan vía ETF — posible soporte estructural",
        }
    return None


def _divergencia_ili(es_max_30d, ili_score, dias_ventana=30):
    if not es_max_30d or ili_score is None:
        return None
    if ili_score < 50:
        return {
            "tipo": "DIVERGENCIA_ILI_ROJA",
            "nota": f"Precio en máximo de {dias_ventana} días pero el ILI está por debajo de 50 — señal de reducir exposición",
        }
    if ili_score < ILI_FUERTE:
        return {
            "tipo": "DIVERGENCIA_ILI_AMARILLA",
            "nota": f"Precio en máximo de {dias_ventana} días pero el ILI no acompaña — señal de cautela",
        }
    return None


def analizar_estado(
    ticker,
    flujo_neto_7d_usd_m,
    funding_pct,
    ili_score=None,
    es_max_30d=None,
    exchange_netflow_neto=None,
    exchange_netflow_unidad="",
):
    """Cruza las capas de señal y devuelve un sesgo consolidado.

    `ticker` es el dict de binance_client.get_ticker() para el activo elegido.
    Todos los parámetros salvo `ticker` son opcionales: si faltan (sin API
    key, sin ETF para el activo, etc.), esa capa queda como "sin_datos" sin
    romper nada ni afectar a las demás.
    """
    sig_precio, txt_precio = _signal_precio(ticker["cambio_24h_pct"])
    sig_etf, txt_etf = _signal_etf(flujo_neto_7d_usd_m)
    sig_funding, txt_funding = _signal_funding(funding_pct)
    sig_ili, txt_ili = _signal_ili(ili_score)
    sig_exchange, txt_exchange = _signal_exchange_netflow(exchange_netflow_neto, exchange_netflow_unidad)

    señales = {
        "precio": {"valor": sig_precio, "detalle": txt_precio},
        "etf": {"valor": sig_etf, "detalle": txt_etf},
        "funding": {"valor": sig_funding, "detalle": txt_funding},
        "ili": {"valor": sig_ili, "detalle": txt_ili},
        "exchange_netflow": {"valor": sig_exchange, "detalle": txt_exchange},
    }

    # Divergencia precio vs. ETF: el caso más informativo (spec del proyecto)
    divergencia = _divergencia_precio_etf(sig_precio, sig_etf)
    # Divergencia precio vs. ILI: "nuevo máximo sin liquidez institucional acompañando"
    divergencia_ili = _divergencia_ili(es_max_30d, ili_score)

    señales_votables = (sig_precio, sig_etf, sig_funding, sig_ili, sig_exchange)
    votos_alcistas = sum(1 for s in señales_votables if s == "alcista")
    votos_bajistas = sum(1 for s in señales_votables if s == "bajista")

    if votos_alcistas >= 2 and votos_alcistas > votos_bajistas:
        sesgo = "ALCISTA"
    elif votos_bajistas >= 2 and votos_bajistas > votos_alcistas:
        sesgo = "BAJISTA"
    elif divergencia:
        sesgo = divergencia["tipo"]
    else:
        sesgo = "NEUTRAL"

    return {
        "sesgo": sesgo,
        "señales": señales,
        "divergencia": divergencia,
        "divergencia_ili": divergencia_ili,
        "flujo_neto_7d_millones_usd": flujo_neto_7d_usd_m,
        "ili_score": ili_score,
        "exchange_netflow_neto": exchange_netflow_neto,
        "votos_alcistas": votos_alcistas,
        "votos_bajistas": votos_bajistas,
    }
