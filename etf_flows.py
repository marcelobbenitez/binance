"""Scraper del flujo diario de ETF spot publicado por Farside Investors.

Farside (https://farside.co.uk/<asset>/) es la fuente gratuita más completa
de flujos netos diarios de los ETF spot en EE.UU., tanto para BTC como para
ETH. No expone una API, así que se parsea la tabla HTML directamente. El
resultado se cachea en memoria por activo porque Farside solo actualiza estos
datos una vez al día (T+1).

Además de los flujos diarios, la misma tabla trae filas de resumen
(Average/Maximum/Minimum del flujo diario total histórico) que se usan como
rango de referencia para el Índice de Liquidez Institucional (ver ili.py).
"""

import re
import time

import requests
from bs4 import BeautifulSoup

FARSIDE_URL_TEMPLATE = "https://farside.co.uk/{asset}/"
CACHE_TTL_SECONDS = 6 * 60 * 60  # los datos son T+1: no hace falta refrescar seguido

_DATE_RE = re.compile(r"^\d{1,2} \w{3} \d{4}$")
_STATS_LABELS = {"average", "maximum", "minimum"}

_cache = {}  # asset -> {"rows": [...], "stats": {...}, "fetched_at": float}


def _parse_num(text):
    """'(24.5)' -> -24.5 · '0.0' -> 0.0 · '-' -> None · '1,119.9' -> 1119.9"""
    s = text.strip().replace(",", "")
    if s in ("", "-", "−"):
        return None
    negative = s.startswith("(") and s.endswith(")")
    if negative:
        s = s[1:-1]
    try:
        value = float(s)
    except ValueError:
        return None
    return -value if negative else value


def _scrape(asset):
    r = requests.get(
        FARSIDE_URL_TEMPLATE.format(asset=asset),
        timeout=15,
        headers={"User-Agent": "Mozilla/5.0 (compatible; CryptoMonitor/1.0)"},
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    table = soup.find("table", class_="etf")
    if table is None:
        raise RuntimeError(f"No se encontró la tabla de flujos ETF en Farside para '{asset}'")

    header_rows = table.find("thead").find_all("tr")
    tickers = [th.get_text(strip=True) for th in header_rows[1].find_all("th")][1:]
    if tickers and tickers[-1] == "":
        # el nombre de la última columna ("Total") solo aparece en la 1ra fila de encabezado
        tickers[-1] = "Total"

    rows = []
    stats = {}
    for tr in table.find("tbody").find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        label = tds[0].get_text(strip=True)
        values = [_parse_num(td.get_text(strip=True)) for td in tds[1:]]

        if _DATE_RE.match(label):
            entry = {"fecha": label}
            for ticker, value in zip(tickers, values):
                entry[ticker] = value
            rows.append(entry)
        elif label.lower() in _STATS_LABELS and values:
            stats[label.lower()] = values[-1]  # última columna = Total entre todos los ETF

    return rows, stats


def get_etf_flows(asset, force_refresh=False):
    """Devuelve la lista de flujos diarios por ETF de `asset` ("btc" / "eth"),
    de más antiguo a más reciente.

    Cada elemento: {"fecha": "28 Sep 2026", "IBIT": 54.8, ..., "Total": 31.0}
    (todos los valores en millones de USD). Usa caché en memoria por activo;
    si el scrape falla pero hay una copia cacheada, devuelve la copia en vez
    de romper.
    """
    return _get_cached(asset, force_refresh)["rows"]


def get_flow_stats(asset, force_refresh=False):
    """Devuelve {'average', 'maximum', 'minimum'} del flujo diario TOTAL
    histórico (en millones de USD) publicado por Farside para `asset`."""
    return _get_cached(asset, force_refresh)["stats"]


def _get_cached(asset, force_refresh=False):
    entry = _cache.setdefault(asset, {"rows": None, "stats": None, "fetched_at": 0.0})
    now = time.time()
    if not force_refresh and entry["rows"] is not None:
        if now - entry["fetched_at"] < CACHE_TTL_SECONDS:
            return entry

    try:
        rows, stats = _scrape(asset)
    except Exception:
        if entry["rows"] is not None:
            return entry
        raise

    entry["rows"] = rows
    entry["stats"] = stats
    entry["fetched_at"] = now
    return entry


def get_net_flow_usd(asset, days=7):
    """Suma el flujo neto total (columna 'Total', en millones de USD) de los
    últimos `days` días con dato publicado para `asset`."""
    flows = get_etf_flows(asset)
    recent = [f for f in flows if f.get("Total") is not None][-days:]
    return sum(f["Total"] for f in recent), recent
