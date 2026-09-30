"""Crypto Monitor — backend Flask.

Sirve la SPA (index.html) y expone endpoints propios, por activo (BTC, ETH,
BNB), para precio de Binance, flujo ETF (scrapeado de Farside, cuando el
activo tiene ETF spot) y el análisis de sesgo alcista/bajista. Todo pasa por
este backend para evitar problemas de CORS/geo-bloqueo en el navegador y para
poder cachear el scrape de Farside.
"""

import os

from flask import Flask, abort, jsonify, request, send_from_directory

import backtest
import binance_client
import etf_flows
import ili
import volatility
from analysis import analizar_estado
from assets_config import ASSETS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ILI_WINDOW_DAYS = 30  # ventana para el chequeo de "nuevo máximo de N días" del ILI
VOL_HORIZONS_DAYS = (7, 14, 30)  # plazos para el rango de movimiento esperado
ALLOWED_KLINE_INTERVALS = {"1h", "4h", "1d"}

app = Flask(__name__, static_folder=None)


def _asset_config(asset):
    cfg = ASSETS.get(asset)
    if cfg is None:
        abort(404, description=f"Activo desconocido: '{asset}'. Válidos: {list(ASSETS)}")
    return cfg


@app.get("/")
def index():
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/api/assets")
def api_assets():
    return jsonify({
        asset: {"label": cfg["label"], "tiene_etf": cfg["farside_slug"] is not None}
        for asset, cfg in ASSETS.items()
    })


@app.get("/api/<asset>/price")
def api_price(asset):
    cfg = _asset_config(asset)
    try:
        return jsonify(binance_client.get_ticker(cfg["symbol"]))
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.get("/api/<asset>/etf-flows")
def api_etf_flows(asset):
    cfg = _asset_config(asset)
    if cfg["farside_slug"] is None:
        return jsonify({"flows": [], "soportado": False})

    days = request.args.get("days", 14, type=int) or 14
    days = max(1, min(days, 400))

    try:
        # El histórico completo (cacheado 24h) también sirve para la vista de
        # ~14 días; evita mantener dos scrapes separados de la misma info.
        flows = etf_flows.get_full_history(cfg["farside_slug"])
        if not flows:
            flows = etf_flows.get_etf_flows(cfg["farside_slug"])
        return jsonify({"flows": flows[-days:], "soportado": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.get("/api/<asset>/klines")
def api_klines(asset):
    cfg = _asset_config(asset)
    interval = request.args.get("interval", "1d")
    if interval not in ALLOWED_KLINE_INTERVALS:
        interval = "1d"
    limit = request.args.get("limit", 180, type=int) or 180
    limit = max(10, min(limit, 500))
    try:
        return jsonify({"interval": interval, "velas": binance_client.get_klines(cfg["symbol"], interval=interval, limit=limit)})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.get("/api/<asset>/backtest")
def api_backtest(asset):
    cfg = _asset_config(asset)
    try:
        resultado = backtest.get_backtest(asset, cfg["symbol"], cfg["farside_slug"])
        return jsonify(resultado)
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.get("/api/<asset>/analysis")
def api_analysis(asset):
    cfg = _asset_config(asset)

    try:
        ticker = binance_client.get_ticker(cfg["symbol"])
    except Exception as e:
        return jsonify({"error": f"No se pudo leer Binance: {e}"}), 502

    funding = binance_client.get_funding_rate(cfg["symbol"])

    flujo_7d, recientes, stats = None, [], None
    if cfg["farside_slug"] is not None:
        try:
            flujo_7d, recientes = etf_flows.get_net_flow_usd(cfg["farside_slug"], days=7)
            stats = etf_flows.get_flow_stats(cfg["farside_slug"])
        except Exception:
            pass

    velas, es_max_30d = [], None
    try:
        velas = binance_client.get_klines(cfg["symbol"], interval="1d", limit=90)
        es_max_30d = ili.es_maximo_de_n_dias(ticker["precio"], velas, dias=ILI_WINDOW_DAYS)
    except Exception:
        pass

    ili_score = ili.compute_score(flujo_7d, len(recientes), stats)

    estado = analizar_estado(ticker, flujo_7d, funding, ili_score=ili_score, es_max_30d=es_max_30d)

    vol_pct = volatility.get_implied_vol_pct(cfg["symbol"])
    vol_fuente = "implicita_deribit"
    if vol_pct is None:
        vol_pct = volatility.get_realized_vol_pct(velas, days=30) if velas else None
        vol_fuente = "historica_realizada_30d"

    movimiento_esperado = None
    if vol_pct is not None:
        movimiento_esperado = {
            "volatilidad_anual_pct": vol_pct,
            "fuente": vol_fuente,
            "horizontes": {
                f"{dias}d": volatility.expected_move(ticker["precio"], vol_pct, dias)
                for dias in VOL_HORIZONS_DAYS
            },
        }

    return jsonify({
        "asset": asset,
        "label": cfg["label"],
        "ticker": ticker,
        "funding_rate_pct": funding,
        "etf_soportado": cfg["farside_slug"] is not None,
        "etf_flujo_7d_dias_con_dato": [r["fecha"] for r in recientes],
        "es_maximo_30d": es_max_30d,
        "analisis": estado,
        "movimiento_esperado": movimiento_esperado,
        "nota_etf": "Los flujos de ETF son T+1 (Farside los publica con el cierre del día anterior en EE.UU.)",
        "nota_ili": "ILI simplificado: normaliza el flujo ETF contra su propio rango histórico; no incluye liquidez USD agregada (ver README).",
        "nota_movimiento": "Rango estadístico de volatilidad (±1 desvío, ~68% bajo supuesto lognormal), no una predicción de precio ni de dirección.",
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
