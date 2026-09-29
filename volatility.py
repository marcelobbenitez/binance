"""Estimación del rango de movimiento esperado — no una predicción de precio.

Esto responde una pregunta distinta a la del sesgo (analysis.py): el sesgo
dice *hacia dónde* podría inclinarse el mercado; esto dice *cuánto* suele
moverse el precio en cierto plazo, sin opinar sobre la dirección. Las dos
cosas se muestran juntas en la app pero son independientes: el rango es
simétrico alrededor del precio actual.

Fuente preferida: el índice DVOL de Deribit (volatilidad implícita anualizada
de las opciones de BTC/ETH, público, sin API key) — es lo que el propio
mercado de opciones está pagando por cobertura, la referencia más legítima
que existe para "cuánto se espera que se mueva" un activo hacia adelante.
BNB no tiene mercado de opciones líquido en Deribit, así que para ese activo
(o si Deribit falla) se usa volatilidad histórica realizada, calculada a
partir de las velas diarias de Binance. Es un fallback más débil porque mira
al pasado, no lo que el mercado espera hacia adelante.

El cálculo del rango asume retornos ~lognormales (aproximación estándar de
opciones), lo cual subestima la probabilidad real de movimientos extremos en
cripto (colas más pesadas que una normal); por eso se lo presenta como una
referencia estadística de "movimientos típicos", no como un límite garantizado.
"""

import math
import statistics
import time

import requests

DERIBIT_URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
DERIBIT_CURRENCY = {"BTCUSDT": "BTC", "ETHUSDT": "ETH"}
CACHE_TTL_SECONDS = 15 * 60

_cache = {}  # symbol -> {"iv_pct": float, "fetched_at": float}


def get_implied_vol_pct(symbol):
    """Volatilidad implícita anualizada (%) del índice DVOL de Deribit para
    `symbol` (ej. "BTCUSDT"). Devuelve `None` si el activo no tiene mercado
    de opciones en Deribit (ej. BNB) o si la consulta falla."""
    currency = DERIBIT_CURRENCY.get(symbol)
    if currency is None:
        return None

    entry = _cache.setdefault(symbol, {"iv_pct": None, "fetched_at": 0.0})
    now = time.time()
    if entry["iv_pct"] is not None and now - entry["fetched_at"] < CACHE_TTL_SECONDS:
        return entry["iv_pct"]

    try:
        end_ms = int(now * 1000)
        start_ms = end_ms - 2 * 60 * 60 * 1000  # últimas 2h alcanza para tener velas recientes
        r = requests.get(
            DERIBIT_URL,
            params={"currency": currency, "start_timestamp": start_ms, "end_timestamp": end_ms, "resolution": "60"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()["result"]["data"]
        if not data:
            return entry["iv_pct"]
        iv_pct = data[-1][4]  # close de la última vela horaria = DVOL más reciente
    except Exception:
        return entry["iv_pct"]

    entry["iv_pct"] = iv_pct
    entry["fetched_at"] = now
    return iv_pct


def get_realized_vol_pct(velas, days=30):
    """Volatilidad histórica anualizada (%), calculada con los retornos
    diarios logarítmicos de las últimas `days` velas. Fallback para cuando no
    hay volatilidad implícita disponible (BNB, o falla de Deribit)."""
    cierres = [v["close"] for v in velas[-(days + 1):] if v["close"] > 0]
    if len(cierres) < 5:
        return None
    retornos = [math.log(cierres[i] / cierres[i - 1]) for i in range(1, len(cierres))]
    if len(retornos) < 2:
        return None
    desvio = statistics.pstdev(retornos)
    return desvio * math.sqrt(365) * 100


def expected_move(precio, vol_anual_pct, dias):
    """Movimiento esperado de ±1 desvío estándar en `dias` calendario,
    escalando la volatilidad anualizada por raíz de tiempo (aprox. estándar
    de opciones: vol_horizonte = vol_anual × sqrt(dias/365)).

    Bajo el supuesto (aproximado) de retornos lognormales, el precio quedaría
    dentro de [precio_min, precio_max] con ~68% de probabilidad. En cripto,
    con colas más pesadas que una normal, la probabilidad real de quedar
    dentro del rango suele ser algo menor a ese 68%.
    """
    if vol_anual_pct is None or precio is None:
        return None
    pct = (vol_anual_pct / 100) * math.sqrt(dias / 365)
    monto = precio * pct
    return {
        "pct": pct * 100,
        "monto": monto,
        "precio_min": precio - monto,
        "precio_max": precio + monto,
    }
