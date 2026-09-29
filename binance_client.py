"""Cliente ligero para los endpoints públicos de Binance usados por Crypto Monitor."""

import requests

SPOT_BASE_URL = "https://data-api.binance.vision"
FUTURES_BASE_URL = "https://fapi.binance.com"


def get_ticker(symbol="BTCUSDT"):
    """Devuelve el estado actual (24h) del par indicado desde el spot público de Binance."""
    r = requests.get(
        f"{SPOT_BASE_URL}/api/v3/ticker/24hr",
        params={"symbol": symbol},
        timeout=10,
    )
    r.raise_for_status()
    d = r.json()

    return {
        "symbol": d["symbol"],
        "precio": float(d["lastPrice"]),
        "cambio_24h_pct": float(d["priceChangePercent"]),
        "max_24h": float(d["highPrice"]),
        "min_24h": float(d["lowPrice"]),
        "volumen_base": float(d["volume"]),
        "volumen_quote": float(d["quoteVolume"]),
    }


def get_funding_rate(symbol="BTCUSDT"):
    """Devuelve el funding rate vigente de futuros perpetuos, en porcentaje.

    Puede fallar por geo-bloqueo de fapi.binance.com en algunas regiones,
    por eso el llamador debe tratar `None` como "dato no disponible".
    """
    try:
        r = requests.get(
            f"{FUTURES_BASE_URL}/fapi/v1/premiumIndex",
            params={"symbol": symbol},
            timeout=10,
        )
        r.raise_for_status()
        d = r.json()
        return float(d["lastFundingRate"]) * 100
    except Exception:
        return None
