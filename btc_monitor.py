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
import ili
import volatility
from analysis import analizar_estado
from assets_config import ASSETS

ILI_WINDOW_DAYS = 30
VOL_HORIZONS_DAYS = (7, 14, 30)

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

    velas, es_max_30d = [], None
    try:
        velas = binance_client.get_klines(cfg["symbol"], interval="1d", limit=90)
        es_max_30d = ili.es_maximo_de_n_dias(ticker["precio"], velas, dias=ILI_WINDOW_DAYS)
    except Exception:
        pass
    ili_score = ili.compute_score(flujo_7d, len(recientes), stats)

    estado = analizar_estado(ticker, flujo_7d, funding, ili_score=ili_score, es_max_30d=es_max_30d)
    print(f"\nSesgo estimado: {estado['sesgo']}")
    for nombre, señal in estado["señales"].items():
        print(f"   [{señal['valor'].upper()}] {nombre}: {señal['detalle']}")
    if estado["divergencia"]:
        print(f"\n   ⚠ {estado['divergencia']['nota']}")
    if estado["divergencia_ili"]:
        print(f"\n   ⚠ {estado['divergencia_ili']['nota']}")

    vol_pct = volatility.get_implied_vol_pct(cfg["symbol"])
    fuente = "implícita, Deribit"
    if vol_pct is None:
        vol_pct = volatility.get_realized_vol_pct(velas, days=30) if velas else None
        fuente = "histórica realizada 30d"

    if vol_pct is not None:
        print(f"\nRango de movimiento esperado (volatilidad anual {vol_pct:.1f}%, {fuente}):")
        for dias in VOL_HORIZONS_DAYS:
            mov = volatility.expected_move(ticker["precio"], vol_pct, dias)
            print(f"   {dias}d (±1 desvío, ~68%): ${mov['precio_min']:,.0f} — ${mov['precio_max']:,.0f} (±{mov['pct']:.1f}%)")
        print("   (rango estadístico, no una predicción de precio ni de dirección)")
    else:
        print("\nRango de movimiento esperado: sin datos de volatilidad disponibles")
    print()


def main():
    for asset, cfg in ASSETS.items():
        analizar_activo(asset, cfg)


if __name__ == "__main__":
    main()
