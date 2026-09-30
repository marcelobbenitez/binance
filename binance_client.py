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


def get_klines(symbol="BTCUSDT", interval="1d", limit=90):
    """Devuelve velas OHLC públicas del spot de Binance, de más antigua a más
    reciente. Se usa tanto para el gráfico de velas como para calcular el
    máximo de N días que necesita el ILI.
    """
    r = requests.get(
        f"{SPOT_BASE_URL}/api/v3/klines",
        params={"symbol": symbol, "interval": interval, "limit": limit},
        timeout=10,
    )
    r.raise_for_status()
    rows = r.json()

    return [
        {
            "time": row[0] // 1000,  # openTime en segundos (lightweight-charts espera UNIX seconds)
            "open": float(row[1]),
            "high": float(row[2]),
            "low": float(row[3]),
            "close": float(row[4]),
            "volume": float(row[5]),
        }
        for row in rows
    ]


def get_historical_funding(symbol, start_ms, end_ms):
    """Devuelve el historial de funding rate (cada 8h) entre `start_ms` y
    `end_ms` (timestamps en milisegundos), paginando de a 1000 registros (el
    máximo por request, ~333 días a razón de 3 pagos por día). Se usa para
    backtest.py, no para el estado en vivo (para eso está get_funding_rate).

    Puede fallar por geo-bloqueo de fapi.binance.com en algunas regiones; el
    llamador debe tratar una lista vacía como "sin datos", no como error.
    """
    resultados = []
    cursor = start_ms
    while cursor < end_ms:
        r = requests.get(
            f"{FUTURES_BASE_URL}/fapi/v1/fundingRate",
            params={"symbol": symbol, "startTime": cursor, "endTime": end_ms, "limit": 1000},
            timeout=15,
        )
        r.raise_for_status()
        lote = r.json()
        if not lote:
            break
        resultados.extend(lote)
        ultimo = lote[-1]["fundingTime"]
        if ultimo <= cursor:
            break
        cursor = ultimo + 1
        if len(lote) < 1000:
            break
    return resultados


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
