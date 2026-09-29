"""Cliente del flujo neto a exchanges (CryptoQuant), la señal on-chain que el
resumen original pedía y que antes quedaba fuera del proyecto por no tener
fuente gratuita.

Requiere una API key propia de CryptoQuant (cuenta paga o de prueba — la
Basic plan es gratis para empezar, pero el endpoint de netflow agregado
puede no estar incluido en el tier free, depende del plan de cada cuenta).
Se lee de la variable de entorno CRYPTOQUANT_API_KEY; si no está configurada,
toda esta capa queda como "sin_datos" en vez de romper la app. Ni esta app ni
el asistente que la generó manejan esa clave por vos: la conseguís vos mismo
en https://cryptoquant.com y la configurás como variable de entorno (local o
en el hosting), nunca hardcodeada en el código.

Netflow positivo = entra más a exchanges de lo que sale (presión de venta
potencial). Netflow negativo = sale más de lo que entra (acumulación /
cold storage), aunque esto no es automáticamente alcista: puede ser un
rebalanceo interno entre hot/cold wallets del mismo exchange, no necesariamente
compra institucional. Ver README para el detalle de esta limitación.
"""

import os
import time

import requests

API_BASE = "https://api.cryptoquant.com/v1"
CACHE_TTL_SECONDS = 6 * 60 * 60  # el dato es ~diario, no hace falta refrescar seguido

_cache = {}  # asset -> {"data": [...], "fetched_at": float}


def _api_key():
    return os.environ.get("CRYPTOQUANT_API_KEY")


def is_configured():
    return bool(_api_key())


def _fetch(asset, limit):
    api_key = _api_key()
    r = requests.get(
        f"{API_BASE}/{asset}/exchange-flows/netflow",
        params={"exchange": "all_exchange", "window": "day", "limit": limit},
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


def get_daily_netflow(asset, days=7, force_refresh=False):
    """Devuelve una lista de {"fecha": "2026-09-28", "netflow": 123.45}
    (en unidades nativas del activo: BTC o ETH; positivo = entra a exchanges,
    negativo = sale) de los últimos `days` días con dato.

    Devuelve `None` si no hay CRYPTOQUANT_API_KEY configurada (capa
    deshabilitada, no es un error).
    """
    if not is_configured():
        return None

    entry = _cache.setdefault(asset, {"data": None, "fetched_at": 0.0})
    now = time.time()
    if not force_refresh and entry["data"] is not None:
        if now - entry["fetched_at"] < CACHE_TTL_SECONDS:
            return entry["data"][-days:]

    try:
        parsed = _fetch(asset, limit=max(days + 2, 10))
    except Exception:
        if entry["data"] is not None:
            return entry["data"][-days:]
        raise

    entry["data"] = parsed
    entry["fetched_at"] = now
    return parsed[-days:]


def get_net_flow_sum(asset, days=7):
    """Devuelve (suma_neta, lista_dias). Si la capa está deshabilitada (sin
    API key) o falla, devuelve (None, []) en vez de romper."""
    try:
        rows = get_daily_netflow(asset, days=days)
    except Exception:
        return None, []
    if rows is None:
        return None, []
    return sum(r["netflow"] for r in rows), rows
