"""Crypto Monitor — versión CLI.

Muestra el estado actual de BTC, ETH y BNB (Binance) y el sesgo alcista/
bajista de cada uno, cruzando precio, flujo neto de ETF spot (Farside,
últimos 7 días, cuando el activo tiene ETF) y funding rate de futuros
perpetuos.

Uso:
    python btc_monitor.py
"""

import sys

import binance_client
import etf_flows
import exchange_netflow
import ili
from analysis import analizar_estado
from assets_config import ASSETS

ILI_WINDOW_DAYS = 30

# En Windows la consola suele usar cp1252, que no puede codificar el símbolo
# de advertencia usado más abajo; forzamos UTF-8 para evitar un crash.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def analizar_activo(asset, cfg):
    print("=" * 60)
    print(f"{cfg['label'].upper()} ({cfg['symbol']})")
    print("=" * 60)

    ticker = binance_client.get_ticker(cfg["symbol"])
    print(f"\nPrecio: ${ticker['precio']:,.2f}")
    print(f"   Cambio 24h: {ticker['cambio_24h_pct']:+.2f}%")
    print(f"   Rango 24h: ${ticker['min_24h']:,.0f} — ${ticker['max_24h']:,.0f}")
    print(f"   Volumen 24h: {ticker['volumen_base']:,.1f} (${ticker['volumen_quote']:,.0f})")

    funding = binance_client.get_funding_rate(cfg["symbol"])
    if funding is not None:
        print(f"\nFunding rate (perp): {funding:+.4f}%")
    else:
        print("\nFunding rate: no disponible (endpoint de futuros bloqueado o caído)")

    flujo_7d, recientes, stats = None, [], None
    if cfg["farside_slug"] is None:
        print("\nETF flows: no aplica (no hay ETF spot aprobado para este activo)")
    else:
        try:
            flujo_7d, recientes = etf_flows.get_net_flow_usd(cfg["farside_slug"], days=7)
            stats = etf_flows.get_flow_stats(cfg["farside_slug"])
            print(f"\nFlujo neto ETF spot (últimos {len(recientes)} días con dato): ${flujo_7d:,.1f}M")
            for f in recientes:
                dato = f"{f['Total']:+.1f}M" if f["Total"] is not None else "sin dato"
                print(f"   {f['fecha']}: {dato}")
        except Exception as e:
            print(f"\nETF flows: no se pudo obtener ({e})")

    es_max_30d = None
    try:
        velas = binance_client.get_klines(cfg["symbol"], interval="1d", limit=ILI_WINDOW_DAYS)
        es_max_30d = ili.es_maximo_de_n_dias(ticker["precio"], velas, dias=ILI_WINDOW_DAYS)
    except Exception:
        pass
    ili_score = ili.compute_score(flujo_7d, len(recientes), stats)

    netflow_neto = None
    if cfg["cryptoquant_asset"] is None:
        print("\nFlujo a exchanges: no aplica (activo no soportado por CryptoQuant en esta app)")
    elif not exchange_netflow.is_configured():
        print("\nFlujo a exchanges: no configurado (definí CRYPTOQUANT_API_KEY para activarlo)")
    else:
        try:
            netflow_neto, dias = exchange_netflow.get_net_flow_sum(cfg["cryptoquant_asset"], days=7)
            print(f"\nFlujo neto a exchanges (últimos {len(dias)} días con dato): {netflow_neto:+,.0f} {cfg['unit']}")
            for d in dias:
                print(f"   {d['fecha']}: {d['netflow']:+,.1f}")
        except Exception as e:
            print(f"\nFlujo a exchanges: no se pudo obtener ({e})")

    estado = analizar_estado(
        ticker, flujo_7d, funding, ili_score=ili_score, es_max_30d=es_max_30d,
        exchange_netflow_neto=netflow_neto, exchange_netflow_unidad=cfg["unit"],
    )
    print(f"\nSesgo estimado: {estado['sesgo']}")
    for nombre, señal in estado["señales"].items():
        print(f"   [{señal['valor'].upper()}] {nombre}: {señal['detalle']}")
    if estado["divergencia"]:
        print(f"\n   ⚠ {estado['divergencia']['nota']}")
    if estado["divergencia_ili"]:
        print(f"\n   ⚠ {estado['divergencia_ili']['nota']}")
    print()


def main():
    for asset, cfg in ASSETS.items():
        analizar_activo(asset, cfg)


if __name__ == "__main__":
    main()
