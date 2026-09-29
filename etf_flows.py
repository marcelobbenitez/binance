"""Scraper del flujo diario de los ETF spot de BTC publicado por Farside Investors.

Farside (https://farside.co.uk/btc/) es la fuente gratuita más completa de
flujos netos diarios de los ETF spot de BTC en EE.UU. No expone una API, así
que se parsea la tabla HTML directamente. El resultado se cachea en memoria
porque Farside solo actualiza estos datos una vez al día (T+1).
"""

import re
import time

import requests
from bs4 import BeautifulSoup

FARSIDE_URL = "https://farside.co.uk/btc/"
CACHE_TTL_SECONDS = 6 * 60 * 60  # los datos son T+1: no hace falta refrescar seguido

_DATE_RE = re.compile(r"^\d{1,2} \w{3} \d{4}$")

_cache = {"data": None, "fetched_at": 0.0}


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


def _scrape():
    r = requests.get(
        FARSIDE_URL,
        timeout=15,
        headers={"User-Agent": "Mozilla/5.0 (compatible; BTCMonitor/1.0)"},
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    table = soup.find("table", class_="etf")
    if table is None:
        raise RuntimeError("No se encontró la tabla de flujos ETF en Farside")

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


def get_etf_flows(force_refresh=False):
    """Devuelve la lista de flujos diarios por ETF, de más antiguo a más reciente.

    Cada elemento: {"fecha": "28 Sep 2026", "IBIT": 54.8, ..., "Total": 31.0}
    (todos los valores en millones de USD). Usa caché en memoria; si el scrape
    falla pero hay una copia cacheada, devuelve la copia en vez de romper.
    """
    now = time.time()
    if not force_refresh and _cache["data"] is not None:
        if now - _cache["fetched_at"] < CACHE_TTL_SECONDS:
            return _cache["data"]

    try:
        rows = _scrape()
    except Exception:
        if _cache["data"] is not None:
            return _cache["data"]
        raise

    _cache["data"] = rows
    _cache["fetched_at"] = now
    return rows


def get_net_flow_usd(days=7):
    """Suma el flujo neto total (columna 'Total', en millones de USD) de los
    últimos `days` días con dato publicado."""
    flows = get_etf_flows()
    recent = [f for f in flows if f.get("Total") is not None][-days:]
    return sum(f["Total"] for f in recent), recent
