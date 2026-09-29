"""Scraper del flujo diario de ETF spot publicado por Farside Investors.

Farside (https://farside.co.uk/<asset>/) es la fuente gratuita más completa
de flujos netos diarios de los ETF spot en EE.UU., tanto para BTC como para
ETH. No expone una API, así que se parsea la tabla HTML directamente. El
resultado se cachea en memoria por activo porque Farside solo actualiza estos
datos una vez al día (T+1).

Además de los flujos diarios, la misma tabla trae filas de resumen
(Average/Maximum/Minimum del flujo diario total histórico) que se usan como
rango de referencia para el Índice de Liquidez Institucional (ver ili.py).

La página normal (`/btc/`, `/eth/`) solo muestra los últimos ~14 días. Para
backtesting (ver backtest.py) hace falta el histórico completo, que vive en
una URL separada (`get_full_history`).
"""

import re
import time

import requests
from bs4 import BeautifulSoup

FARSIDE_URL_TEMPLATE = "https://farside.co.uk/{asset}/"
FULL_HISTORY_URL = {
    "btc": "https://farside.co.uk/bitcoin-etf-flow-all-data/",
    "eth": "https://farside.co.uk/ethereum-etf-flow-all-data/",
}
CACHE_TTL_SECONDS = 6 * 60 * 60  # los datos son T+1: no hace falta refrescar seguido
FULL_HISTORY_CACHE_TTL_SECONDS = 24 * 60 * 60  # histórico completo: alcanza con 1 vez al día

_DATE_RE = re.compile(r"^\d{1,2} \w{3} \d{4}$")
_STATS_LABELS = {"average", "maximum", "minimum"}

_cache = {}  # asset -> {"rows": [...], "stats": {...}, "fetched_at": float}
_full_history_cache = {}  # asset -> {"rows": [...], "fetched_at": float}


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


def _scrape_url(url):
    r = requests.get(
        url,
        timeout=20,
        headers={"User-Agent": "Mozilla/5.0 (compatible; CryptoMonitor/1.0)"},
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    table = soup.find("table", class_="etf")
    if table is None:
        raise RuntimeError(f"No se encontró la tabla de flujos ETF en {url}")

    # La página normal (últimos ~14 días) tiene 3 filas de encabezado (íconos,
    # nombres de ticker, fees en %); la página de histórico completo tiene 1
    # sola fila con los nombres ya completos (incluido "Total"). En vez de
    # asumir una posición fija, elegimos la fila con más celdas que parezcan
    # nombres de verdad (no vacías, no un porcentaje de fee).
    header_rows = table.find("thead").find_all("tr")

    def _fila_de_nombres(tr):
        celdas = [th.get_text(strip=True) for th in tr.find_all("th")][1:]
        return celdas, sum(1 for c in celdas if c and not re.match(r"^\d+(\.\d+)?%$", c))

    candidatos = [_fila_de_nombres(tr) for tr in header_rows]
    tickers, _ = max(candidatos, key=lambda c: c[1])
    if tickers and tickers[-1] == "":
        # el nombre de la última columna ("Total") solo aparece en la fila de íconos
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
    de más antiguo a más reciente (últimos ~14 días que muestra la página
    normal de Farside).

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
        rows, stats = _scrape_url(FARSIDE_URL_TEMPLATE.format(asset=asset))
    except Exception:
        if entry["rows"] is not None:
            return entry
        raise

    entry["rows"] = rows
    entry["stats"] = stats
    entry["fetched_at"] = now
    return entry


def get_full_history(asset, force_refresh=False):
    """Devuelve el histórico COMPLETO de flujos diarios de `asset` ("btc" /
    "eth", los únicos con página de histórico completo en Farside), desde el
    lanzamiento del ETF hasta hoy. Se usa para backtest.py; no se pide en
    cada request porque son ~700 filas y Farside solo actualiza 1 vez al día.
    """
    url = FULL_HISTORY_URL.get(asset)
    if url is None:
        return []

    entry = _full_history_cache.setdefault(asset, {"rows": None, "fetched_at": 0.0})
    now = time.time()
    if not force_refresh and entry["rows"] is not None:
        if now - entry["fetched_at"] < FULL_HISTORY_CACHE_TTL_SECONDS:
            return entry["rows"]

    try:
        rows, _ = _scrape_url(url)
    except Exception:
        if entry["rows"] is not None:
            return entry["rows"]
        raise

    entry["rows"] = rows
    entry["fetched_at"] = now
    return rows


def get_net_flow_usd(asset, days=7):
    """Suma el flujo neto total (columna 'Total', en millones de USD) de los
    últimos `days` días con dato publicado para `asset`."""
    flows = get_etf_flows(asset)
    recent = [f for f in flows if f.get("Total") is not None][-days:]
    return sum(f["Total"] for f in recent), recent
