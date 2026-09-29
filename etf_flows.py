"""Scraper del flujo diario de ETF spot publicado por Farside Investors.

Farside (https://farside.co.uk/<asset>/) es la fuente gratuita más completa
de flujos netos diarios de los ETF spot en EE.UU., tanto para BTC como para
ETH. No expone una API, así que se parsea la tabla HTML directamente. El
resultado se cachea en memoria por activo porque Farside solo actualiza estos
datos una vez al día (T+1).
"""

import re
import time

import requests
from bs4 import BeautifulSoup

FARSIDE_URL_TEMPLATE = "https://farside.co.uk/{asset}/"
CACHE_TTL_SECONDS = 6 * 60 * 60  # los datos son T+1: no hace falta refrescar seguido

_DATE_RE = re.compile(r"^\d{1,2} \w{3} \d{4}$")

_cache = {}  # asset -> {"data": [...], "fetched_at": float}


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
    for tr in table.find("tbody").find_all("tr"):
        tds = tr.find_all("td")
        if not tds:
            continue
        date_text = tds[0].get_text(strip=True)
        if not _DATE_RE.match(date_text):
            continue  # descarta filas de resumen (Total/Average/Maximum/Minimum)

        values = [_parse_num(td.get_text(strip=True)) for td in tds[1:]]
        entry = {"fecha": date_text}
        for ticker, value in zip(tickers, values):
            entry[ticker] = value
        rows.append(entry)

    return rows


def get_etf_flows(asset, force_refresh=False):
    """Devuelve la lista de flujos diarios por ETF de `asset` ("btc" / "eth"),
    de más antiguo a más reciente.

    Cada elemento: {"fecha": "28 Sep 2026", "IBIT": 54.8, ..., "Total": 31.0}
    (todos los valores en millones de USD). Usa caché en memoria por activo;
    si el scrape falla pero hay una copia cacheada, devuelve la copia en vez
    de romper.
    """
    entry = _cache.setdefault(asset, {"data": None, "fetched_at": 0.0})
    now = time.time()
    if not force_refresh and entry["data"] is not None:
        if now - entry["fetched_at"] < CACHE_TTL_SECONDS:
            return entry["data"]

    try:
        rows = _scrape(asset)
    except Exception:
        if entry["data"] is not None:
            return entry["data"]
        raise

    entry["data"] = rows
    entry["fetched_at"] = now
    return rows


def get_net_flow_usd(asset, days=7):
    """Suma el flujo neto total (columna 'Total', en millones de USD) de los
    últimos `days` días con dato publicado para `asset`."""
    flows = get_etf_flows(asset)
    recent = [f for f in flows if f.get("Total") is not None][-days:]
    return sum(f["Total"] for f in recent), recent
