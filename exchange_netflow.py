"""Cliente del flujo neto a exchanges (CryptoQuant), la señal on-chain que el
resumen original pedía y que antes quedaba fuera del proyecto por no tener
fuente gratuita.

Requiere una API key propia de CryptoQuant. Se lee de la variable de entorno
CRYPTOQUANT_API_KEY; si no está configurada, toda esta capa queda como
"sin_datos" en vez de romper la app. Ni esta app ni el asistente que la
generó manejan esa clave por vos: la conseguís vos mismo en
https://cryptoquant.com y la configurás como variable de entorno (local o en
el hosting), nunca hardcodeada en el código.

Se consulta el netflow de un exchange puntual (`DEFAULT_EXCHANGE`, por
defecto "binance") en vez del agregado "all_exchange". En pruebas contra
producción, ambas variantes (`all_exchange` y `binance`) devolvieron 403
Forbidden con la misma API key — un 403 de CryptoQuant significa key válida
pero plan sin acceso a ese endpoint (a diferencia de un 401 por key
inválida), así que el problema parece ser el endpoint `exchange-flows/netflow`
en general para ese plan, no el parámetro `exchange` elegido. Se dejó
"binance" como default porque encaja temáticamente con el resto de la app
(que ya gira en torno a datos de Binance), no porque se haya confirmado que
evita el 403.

Netflow positivo = entra más al exchange de lo que sale (presión de venta
potencial). Netflow negativo = sale más de lo que entra (acumulación /
cold storage), aunque esto no es automáticamente alcista: puede ser un
rebalanceo interno entre hot/cold wallets del mismo exchange, no necesariamente
compra institucional. Ver README para el detalle de esta limitación.
"""

import os
import sys
import time

import requests

API_BASE = "https://api.cryptoquant.com/v1"
CACHE_TTL_SECONDS = 6 * 60 * 60  # el dato es ~diario, no hace falta refrescar seguido

# El agregado "all_exchange" devuelve 403 en planes que no son Enterprise.
# "binance" (un exchange puntual) suele estar disponible en planes más bajos,
# y además encaja con que el resto de la app ya gira en torno a datos de
# Binance. Si tu plan de CryptoQuant sí cubre "all_exchange", podés cambiar
# esta constante.
DEFAULT_EXCHANGE = "binance"

_cache = {}  # asset -> {"data": [...], "fetched_at": float}


def _api_key():
    return os.environ.get("CRYPTOQUANT_API_KEY")


def is_configured():
    return bool(_api_key())


def _fetch(asset, limit, exchange):
    api_key = _api_key()
    r = requests.get(
        f"{API_BASE}/{asset}/exchange-flows/netflow",
        params={"exchange": exchange, "window": "day", "limit": limit},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15,
    )
    r.raise_for_status()
    payload = r.json()
    rows = payload.get("result", {}).get("data", [])

    parsed = [
        {"fecha": row["date"], "netflow": row["netflow_total"]}
        for row in rows
        if row.get("date") and row.get("netflow_total") is not None
    ]
    parsed.sort(key=lambda r: r["fecha"])
    return parsed


def get_daily_netflow(asset, days=7, force_refresh=False, exchange=DEFAULT_EXCHANGE):
    """Devuelve una lista de {"fecha": "2026-09-28", "netflow": 123.45}
    (en unidades nativas del activo: BTC o ETH; positivo = entra a `exchange`,
    negativo = sale) de los últimos `days` días con dato.

    Devuelve `None` si no hay CRYPTOQUANT_API_KEY configurada (capa
    deshabilitada, no es un error).
    """
    if not is_configured():
        return None

    cache_key = f"{asset}:{exchange}"
    entry = _cache.setdefault(cache_key, {"data": None, "fetched_at": 0.0})
    now = time.time()
    if not force_refresh and entry["data"] is not None:
        if now - entry["fetched_at"] < CACHE_TTL_SECONDS:
            return entry["data"][-days:]

    try:
        parsed = _fetch(asset, limit=max(days + 2, 10), exchange=exchange)
    except Exception as e:
        # Log seguro: str(e) de un HTTPError de `requests` trae URL y status,
        # nunca la Authorization header, así que no expone la API key.
        print(f"[exchange_netflow] error al pedir netflow de '{asset}' ({exchange}): {e}", file=sys.stderr)
        if entry["data"] is not None:
            return entry["data"][-days:]
        raise

    entry["data"] = parsed
    entry["fetched_at"] = now
    return parsed[-days:]


def get_net_flow_sum(asset, days=7, exchange=DEFAULT_EXCHANGE):
    """Devuelve (suma_neta, lista_dias). Si la capa está deshabilitada (sin
    API key) o falla, devuelve (None, []) en vez de romper."""
    try:
        rows = get_daily_netflow(asset, days=days, exchange=exchange)
    except Exception:
        return None, []
    if rows is None:
        return None, []
    return sum(r["netflow"] for r in rows), rows
