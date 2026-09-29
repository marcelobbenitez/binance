"""Crypto Monitor — backend Flask.

Sirve la SPA (index.html) y expone endpoints propios, por activo (BTC, ETH,
BNB), para precio de Binance, flujo ETF (scrapeado de Farside, cuando el
activo tiene ETF spot) y el análisis de sesgo alcista/bajista. Todo pasa por
este backend para evitar problemas de CORS/geo-bloqueo en el navegador y para
poder cachear el scrape de Farside.
"""

import os

from flask import Flask, abort, jsonify, send_from_directory

import binance_client
import etf_flows
import exchange_netflow
import ili
from analysis import analizar_estado
from assets_config import ASSETS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ILI_WINDOW_DAYS = 30  # ventana para el chequeo de "nuevo máximo de N días" del ILI

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
        asset: {
            "label": cfg["label"],
            "tiene_etf": cfg["farside_slug"] is not None,
            "tiene_exchange_netflow": cfg["cryptoquant_asset"] is not None and exchange_netflow.is_configured(),
        }
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
    try:
        flows = etf_flows.get_etf_flows(cfg["farside_slug"])
        return jsonify({"flows": flows[-14:], "soportado": True})  # ~2 semanas alcanza para el gráfico
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.get("/api/<asset>/exchange-netflow")
def api_exchange_netflow(asset):
    cfg = _asset_config(asset)
    if cfg["cryptoquant_asset"] is None:
        return jsonify({"dias": [], "soportado": False, "razon": "activo_no_soportado"})
    if not exchange_netflow.is_configured():
        return jsonify({"dias": [], "soportado": False, "razon": "sin_api_key"})
    try:
        _, dias = exchange_netflow.get_net_flow_sum(cfg["cryptoquant_asset"], days=14)
        return jsonify({"dias": dias, "soportado": True, "unidad": cfg["unit"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.get("/api/<asset>/klines")
def api_klines(asset):
    cfg = _asset_config(asset)
    interval = "1d"
    try:
        return jsonify({"interval": interval, "velas": binance_client.get_klines(cfg["symbol"], interval=interval, limit=90)})
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

    es_max_30d = None
    try:
        velas = binance_client.get_klines(cfg["symbol"], interval="1d", limit=ILI_WINDOW_DAYS)
        es_max_30d = ili.es_maximo_de_n_dias(ticker["precio"], velas, dias=ILI_WINDOW_DAYS)
    except Exception:
        pass

    ili_score = ili.compute_score(flujo_7d, len(recientes), stats)

    exchange_netflow_neto = None
    if cfg["cryptoquant_asset"] is not None:
        try:
            exchange_netflow_neto, _ = exchange_netflow.get_net_flow_sum(cfg["cryptoquant_asset"], days=7)
        except Exception:
            pass

    estado = analizar_estado(
        ticker, flujo_7d, funding,
        ili_score=ili_score, es_max_30d=es_max_30d,
        exchange_netflow_neto=exchange_netflow_neto, exchange_netflow_unidad=cfg["unit"],
    )

    return jsonify({
        "asset": asset,
        "label": cfg["label"],
        "ticker": ticker,
        "funding_rate_pct": funding,
        "etf_soportado": cfg["farside_slug"] is not None,
        "etf_flujo_7d_dias_con_dato": [r["fecha"] for r in recientes],
        "exchange_netflow_soportado": cfg["cryptoquant_asset"] is not None and exchange_netflow.is_configured(),
        "es_maximo_30d": es_max_30d,
        "analisis": estado,
        "nota_etf": "Los flujos de ETF son T+1 (Farside los publica con el cierre del día anterior en EE.UU.)",
        "nota_ili": "ILI simplificado: normaliza el flujo ETF contra su propio rango histórico; no incluye liquidez USD agregada (ver README).",
        "nota_exchange_netflow": "Requiere CRYPTOQUANT_API_KEY propia (no incluida); sin ella esta capa queda en \"sin_datos\".",
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
