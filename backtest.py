"""Backtesting histórico del sesgo: frecuencia empírica de que el precio haya
subido o bajado N días después de cada sesgo pasado.

Responde la pregunta "¿qué probabilidad hay de que suba o baje?" de la única
forma que no es inventar un número: reconstruyendo, día por día desde que
existen los ETF, el mismo sesgo que analysis.analizar_estado() calcula en
vivo (usando solo datos disponibles hasta ese día, sin mirar al futuro), y
comparándolo con el retorno real que tuvo el precio 7/14/30 días después. El
resultado es una frecuencia empírica con su propio tamaño de muestra a la
vista — no una predicción.

Limitaciones honestas (ver también README):
- Los ETF de BTC/ETH existen desde 2024/2025, así que la muestra es chica
  (unos cientos de días). BNB no tiene ETF, así que su backtest usa solo
  precio + funding.
- Las ventanas de retorno futuro se solapan día a día (el resultado del día
  10 y el del día 11 comparten casi todos los mismos precios), así que no son
  observaciones estadísticamente independientes entre sí. El "N" es el número
  de días de la muestra, no de eventos independientes — esto es una
  frecuencia descriptiva, no un test de hipótesis con significancia estadística.
- Que un patrón se haya repetido en el pasado no garantiza que se repita.
"""

import datetime as dt
import time

import binance_client
import etf_flows
import ili
from analysis import analizar_estado

HORIZONS_DAYS = (7, 14, 30)
CACHE_TTL_SECONDS = 12 * 60 * 60  # es historia: no hace falta recalcular seguido
BNB_LOOKBACK_DAYS = 400  # sin ETF: ventana fija razonable para precio+funding

_cache = {}  # asset -> {"resultado": {...}, "fetched_at": float}

_FULL_HISTORY_ASSET = {"btc", "eth"}  # los únicos con página de histórico completo en Farside


def _parse_fecha(fecha):
    return dt.datetime.strptime(fecha, "%d %b %Y").date()


def _funding_diario(symbol, start_date, end_date):
    """{'2024-01-11': funding_pct_promedio_del_dia, ...}. Dict vacío si falla
    (geo-bloqueo de futuros, etc.) — el backtest sigue sin esa señal."""
    try:
        start_ms = int(dt.datetime.combine(start_date, dt.time()).timestamp() * 1000)
        end_ms = int(time.time() * 1000)
        crudo = binance_client.get_historical_funding(symbol, start_ms, end_ms)
    except Exception:
        return {}

    por_dia = {}
    for fila in crudo:
        fecha = dt.datetime.utcfromtimestamp(fila["fundingTime"] / 1000).date()
        por_dia.setdefault(fecha, []).append(float(fila["fundingRate"]) * 100)
    return {fecha: sum(vals) / len(vals) for fecha, vals in por_dia.items()}


def _compute(asset, symbol, farside_slug):
    etf_por_fecha = {}
    if farside_slug is not None and asset in _FULL_HISTORY_ASSET:
        filas = etf_flows.get_full_history(asset)
        for fila in filas:
            etf_por_fecha[_parse_fecha(fila["fecha"])] = fila.get("Total")

    fecha_inicio = min(etf_por_fecha) if etf_por_fecha else (dt.date.today() - dt.timedelta(days=BNB_LOOKBACK_DAYS))
    dias_necesarios = (dt.date.today() - fecha_inicio).days + 5

    velas = binance_client.get_klines(symbol, interval="1d", limit=min(dias_necesarios, 1000))
    precios_por_fecha = {}
    for v in velas:
        fecha = dt.datetime.utcfromtimestamp(v["time"]).date()
        precios_por_fecha[fecha] = v
    fechas = sorted(precios_por_fecha)

    funding_por_fecha = _funding_diario(symbol, fecha_inicio, dt.date.today())

    resultados = {}  # sesgo -> "Nd" -> {"n":, "subio":}
    minimo_hist = maximo_hist = None
    primera_fecha_procesada, ultima_fecha_procesada, dias_procesados = None, None, 0

    for i, fecha in enumerate(fechas):
        if i < 7 or fecha < fecha_inicio:
            continue  # necesitamos 7 días previos de precio, y no días de antes del ETF

        vela_hoy = precios_por_fecha[fecha]
        vela_ayer = precios_por_fecha[fechas[i - 1]]
        if vela_ayer["close"] <= 0:
            continue
        cambio_pct = (vela_hoy["close"] - vela_ayer["close"]) / vela_ayer["close"] * 100

        flujo_7d, dias_con_dato, stats_hoy = None, 0, None
        if etf_por_fecha:
            ventana = [fecha - dt.timedelta(days=k) for k in range(7)]
            valores = [etf_por_fecha[f] for f in ventana if etf_por_fecha.get(f) is not None]
            if valores:
                flujo_7d = sum(valores)
                dias_con_dato = len(valores)

            valor_hoy = etf_por_fecha.get(fecha)
            if valor_hoy is not None:
                minimo_hist = valor_hoy if minimo_hist is None else min(minimo_hist, valor_hoy)
                maximo_hist = valor_hoy if maximo_hist is None else max(maximo_hist, valor_hoy)
            if minimo_hist is not None:
                stats_hoy = {"minimum": minimo_hist, "maximum": maximo_hist}

        ili_score = ili.compute_score(flujo_7d, dias_con_dato, stats_hoy)

        velas_30 = [precios_por_fecha[f] for f in fechas[max(0, i - 29): i + 1]]
        es_max_30d = ili.es_maximo_de_n_dias(vela_hoy["close"], velas_30, dias=30)

        funding_pct = funding_por_fecha.get(fecha)

        ticker_historico = {"cambio_24h_pct": cambio_pct}
        estado = analizar_estado(
            ticker_historico, flujo_7d, funding_pct, ili_score=ili_score, es_max_30d=es_max_30d
        )
        sesgo = estado["sesgo"]

        dias_procesados += 1
        if primera_fecha_procesada is None:
            primera_fecha_procesada = fecha
        ultima_fecha_procesada = fecha

        for h in HORIZONS_DAYS:
            j = i + h
            if j >= len(fechas):
                continue
            precio_futuro = precios_por_fecha[fechas[j]]["close"]
            subio = precio_futuro > vela_hoy["close"]
            bucket = resultados.setdefault(sesgo, {}).setdefault(f"{h}d", {"n": 0, "subio": 0})
            bucket["n"] += 1
            if subio:
                bucket["subio"] += 1

    for horizontes in resultados.values():
        for datos in horizontes.values():
            datos["bajo"] = datos["n"] - datos["subio"]
            datos["prob_subida"] = datos["subio"] / datos["n"] if datos["n"] else None

    return {
        "por_sesgo": resultados,
        "desde": primera_fecha_procesada.isoformat() if primera_fecha_procesada else None,
        "hasta": ultima_fecha_procesada.isoformat() if ultima_fecha_procesada else None,
        "dias_analizados": dias_procesados,
        "tiene_funding": bool(funding_por_fecha),
        "tiene_etf": bool(etf_por_fecha),
    }


def get_backtest(asset, symbol, farside_slug, force_refresh=False):
    """Backtest completo cacheado (12h) para `asset`. Ver `_compute` para el
    detalle del cálculo."""
    entry = _cache.setdefault(asset, {"resultado": None, "fetched_at": 0.0})
    now = time.time()
    if not force_refresh and entry["resultado"] is not None:
        if now - entry["fetched_at"] < CACHE_TTL_SECONDS:
            return entry["resultado"]

    try:
        resultado = _compute(asset, symbol, farside_slug)
    except Exception:
        if entry["resultado"] is not None:
            return entry["resultado"]
        raise

    entry["resultado"] = resultado
    entry["fetched_at"] = now
    return resultado
