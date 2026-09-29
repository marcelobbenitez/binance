"""Config compartida de los activos que soporta la app.

`farside_slug` es la ruta de Farside Investors para el flujo de ETF spot de
ese activo (https://farside.co.uk/<slug>/). BNB no tiene ETF spot aprobado en
EE.UU., así que queda en `None` y esa capa de señal se reporta como
"sin_datos" en vez de intentar scrapear algo que no existe.

`cryptoquant_asset` es el identificador de activo que usa la API de
CryptoQuant (https://api.cryptoquant.com/v1/<cryptoquant_asset>/exchange-flows/netflow)
para el flujo neto a exchanges. Igual que con Farside, BNB queda en `None`
porque no está verificado en su catálogo; ver exchange_netflow.py.

`unit` es el ticker nativo del activo (para mostrar cantidades, ej. "1,234 BTC").
"""

ASSETS = {
    "btc": {"symbol": "BTCUSDT", "farside_slug": "btc", "cryptoquant_asset": "btc", "label": "Bitcoin", "unit": "BTC"},
    "eth": {"symbol": "ETHUSDT", "farside_slug": "eth", "cryptoquant_asset": "eth", "label": "Ethereum", "unit": "ETH"},
    "bnb": {"symbol": "BNBUSDT", "farside_slug": None, "cryptoquant_asset": None, "label": "BNB", "unit": "BNB"},
}
