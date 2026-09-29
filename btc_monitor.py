"""BTC Monitor — versión CLI.

Muestra el estado actual de BTC/USDT (Binance) y el sesgo alcista/bajista
cruzando precio, flujo neto de ETF spot (Farside, últimos 7 días) y funding
rate de futuros perpetuos.

Uso:
    python btc_monitor.py
"""

import sys

import binance_client
import etf_flows
from analysis import analizar_estado

# En Windows la consola suele usar cp1252, que no puede codificar el símbolo
# de advertencia usado más abajo; forzamos UTF-8 para evitar un crash.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")


def main():
    print("=" * 60)
    print("MONITOR BTC — ESTADO Y FLUJO INSTITUCIONAL")
    print("=" * 60)

    btc = binance_client.get_btc_ticker()
    print(f"\nBTC: ${btc['precio']:,.2f}")
    print(f"   Cambio 24h: {btc['cambio_24h_pct']:+.2f}%")
    print(f"   Rango 24h: ${btc['min_24h']:,.0f} — ${btc['max_24h']:,.0f}")
    print(f"   Volumen 24h: {btc['volumen_btc']:,.1f} BTC (${btc['volumen_usdt']:,.0f})")

    funding = binance_client.get_funding_rate()
    if funding is not None:
        print(f"\nFunding rate (perp): {funding:+.4f}%")
    else:
        print("\nFunding rate: no disponible (endpoint de futuros bloqueado o caído)")

    try:
        flujo_7d, recientes = etf_flows.get_net_flow_usd(days=7)
        print(f"\nFlujo neto ETF spot (últimos {len(recientes)} días con dato): ${flujo_7d:,.1f}M")
        for f in recientes:
            print(f"   {f['fecha']}: {f['Total']:+.1f}M" if f["Total"] is not None else f"   {f['fecha']}: sin dato")
    except Exception as e:
        print(f"\nETF flows: no se pudo obtener ({e})")
        flujo_7d = None

    estado = analizar_estado(btc, flujo_7d, funding)
    print(f"\nSesgo estimado: {estado['sesgo']}")
    for nombre, señal in estado["señales"].items():
        print(f"   [{señal['valor'].upper()}] {nombre}: {señal['detalle']}")
    if estado["divergencia"]:
        print(f"\n   ⚠ {estado['divergencia']['nota']}")


if __name__ == "__main__":
    main()
