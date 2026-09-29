"""Config compartida de los activos que soporta la app.

`farside_slug` es la ruta de Farside Investors para el flujo de ETF spot de
ese activo (https://farside.co.uk/<slug>/). BNB no tiene ETF spot aprobado en
EE.UU., así que queda en `None` y esa capa de señal se reporta como
"sin_datos" en vez de intentar scrapear algo que no existe.

`unit` es el ticker nativo del activo (para mostrar cantidades, ej. "1,234 BTC").
"""

ASSETS = {
    "btc": {"symbol": "BTCUSDT", "farside_slug": "btc", "label": "Bitcoin", "unit": "BTC"},
    "eth": {"symbol": "ETHUSDT", "farside_slug": "eth", "label": "Ethereum", "unit": "ETH"},
    "bnb": {"symbol": "BNBUSDT", "farside_slug": None, "label": "BNB", "unit": "BNB"},
}
