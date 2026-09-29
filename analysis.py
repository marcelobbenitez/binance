"""Cruce de señales para estimar sesgo alcista/bajista de un activo.

Sirve tanto para BTC como para ETH o BNB: no se usa una sola métrica, se
cruzan precio spot, flujo neto de ETF (7 días, cuando el activo tiene ETF
spot) y funding rate de futuros perpetuos. El flujo neto a exchanges
(retiros/depósitos on-chain) queda fuera porque requiere una API on-chain de
pago (CryptoQuant/Glassnode); ver README para el detalle de esta limitación.
"""

FUNDING_OVERHEATED_PCT = 0.05   # funding > esto: posicionamiento largo excesivo
FUNDING_HEALTHY_MIN_PCT = 0.0   # funding en [0, OVERHEATED]: alcista sano


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


def analizar_estado(ticker, flujo_neto_7d_usd_m, funding_pct):
    """Cruza las tres capas de señal y devuelve un sesgo consolidado.

    `ticker` es el dict de binance_client.get_ticker() para el activo elegido.
    """
    sig_precio, txt_precio = _signal_precio(ticker["cambio_24h_pct"])
    sig_etf, txt_etf = _signal_etf(flujo_neto_7d_usd_m)
    sig_funding, txt_funding = _signal_funding(funding_pct)

    señales = {
        "precio": {"valor": sig_precio, "detalle": txt_precio},
        "etf": {"valor": sig_etf, "detalle": txt_etf},
        "funding": {"valor": sig_funding, "detalle": txt_funding},
    }

    # Divergencia precio vs. ETF: el caso más informativo (spec del proyecto)
    divergencia = None
    if sig_precio == "alcista" and sig_etf == "bajista":
        divergencia = {
            "tipo": "DIVERGENCIA_AMARILLA",
            "nota": "Precio sube pero las instituciones retiran capital vía ETF — señal de cautela",
        }
    elif sig_precio == "bajista" and sig_etf == "alcista":
        divergencia = {
            "tipo": "DIVERGENCIA_VERDE",
            "nota": "Precio baja pero las instituciones acumulan vía ETF — posible soporte estructural",
        }

    votos_alcistas = sum(1 for s in (sig_precio, sig_etf, sig_funding) if s == "alcista")
    votos_bajistas = sum(1 for s in (sig_precio, sig_etf, sig_funding) if s == "bajista")

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
        "flujo_neto_7d_millones_usd": flujo_neto_7d_usd_m,
        "votos_alcistas": votos_alcistas,
        "votos_bajistas": votos_bajistas,
    }
