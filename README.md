# BTC Monitor

App para monitorear el estado de Bitcoin en tiempo real usando datos públicos
de Binance, cruzados con el flujo institucional de los ETF spot de BTC y el
funding rate de futuros, para estimar si el mercado está en sesgo alcista o
bajista.

## Qué muestra

- Precio actual de BTC/USDT, cambio 24h, rango alto/bajo y volumen.
- Flujo neto diario de los ETF spot de BTC (IBIT, FBTC, GBTC, ARKB, etc.),
  scrapeado de Farside Investors.
- Funding rate de futuros perpetuos BTC/USDT.
- Un sesgo consolidado (**ALCISTA** / **BAJISTA** / **NEUTRAL** /
  **DIVERGENCIA**) que cruza las tres señales anteriores, en vez de mirar solo
  el precio.

## Estructura

```
btc-monitor/
├── app.py              # Backend Flask: sirve index.html + API propia
├── binance_client.py   # Cliente de los endpoints públicos de Binance
├── etf_flows.py        # Scraper + caché del flujo ETF (Farside)
├── analysis.py         # Lógica de cruce de señales (sesgo alcista/bajista)
├── btc_monitor.py       # Versión CLI (usa los mismos módulos)
├── index.html           # Frontend (SPA de un solo archivo)
├── requirements.txt
└── .gitignore
```

## Uso rápido (app completa, recomendado)

```bash
pip install -r requirements.txt
python app.py
```

Abrí `http://127.0.0.1:5000` en el navegador. La página se refresca sola cada
30 segundos y muestra precio, flujo ETF y el sesgo estimado.

El backend existe principalmente para scrapear Farside del lado del servidor
(evita problemas de CORS y permite cachear el resultado, ya que el dato es
T+1 y no tiene sentido pedirlo en cada refresco).

## Uso solo como CLI

```bash
pip install -r requirements.txt
python btc_monitor.py
```

## Uso mínimo (solo precio, sin backend)

Si abrís `index.html` directamente como archivo (sin correr `app.py`), la
tarjeta de precio sigue funcionando porque hace fallback a
`data-api.binance.vision` directo desde el navegador. Las tarjetas de sesgo y
flujo ETF van a pedir que levantes el backend, porque dependen del scraper de
Farside.

## Fuentes de datos

- **Binance** (público, sin API key):
  `https://data-api.binance.vision/api/v3/ticker/24hr?symbol=BTCUSDT`
  (usa este dominio y no `api.binance.com`: es el endpoint pensado para
  consumo público y no sufre el geo-bloqueo que sí afecta a `api.binance.com`
  en algunos países).
- **Funding rate**: `https://fapi.binance.com/fapi/v1/premiumIndex` (público).
- **ETF flows**: `https://farside.co.uk/btc/` (scraping de la tabla HTML,
  única fuente gratuita con el histórico completo de flujos diarios).

## Cómo se calcula el sesgo

Se cruzan tres capas de señal (`analysis.py`):

| Señal              | Alcista                      | Bajista                          |
|--------------------|-------------------------------|-----------------------------------|
| Precio (24h)       | Variación positiva            | Variación negativa                |
| Flujo ETF (7 días) | Inflow neto positivo          | Outflow neto                      |
| Funding rate       | Positivo pero no extremo      | Negativo persistente (deleveraging)|

Si al menos dos señales coinciden, el sesgo se marca ALCISTA o BAJISTA. El
caso más informativo es la **divergencia** entre precio y flujo ETF:

- Precio sube + ETF con outflow → `DIVERGENCIA_AMARILLA` (cautela: el rally
  no está acompañado de entrada institucional).
- Precio baja + ETF con inflow → `DIVERGENCIA_VERDE` (posible acumulación
  institucional pese a la caída de precio).

### Por qué no se incluye el flujo neto a exchanges (retiros/depósitos)

Es una de las cuatro señales del análisis original, pero no tiene una fuente
gratuita y en tiempo real: requiere una API on-chain de pago (CryptoQuant,
Glassnode). Además, un retiro de exchange no es automáticamente alcista: puede
ser un rebalanceo interno entre hot/cold wallets, no necesariamente
acumulación. Queda documentado acá como limitación conocida, no como bug.

## Limitaciones prácticas

- Los datos de ETF son **T+1**: Farside los publica con el cierre del día
  hábil anterior en EE.UU., no en tiempo real.
- El funding rate puede no estar disponible si `fapi.binance.com` está
  geo-bloqueado desde tu región; la app lo maneja como "sin datos" en vez de
  romper.
- Respetá los límites de peso de la API de Binance (6.000 unidades/minuto).
  El polling de esta app (cada 30s, 1 request liviano) está muy por debajo.

## Posibles mejoras futuras

- Reemplazar el polling por WebSocket (`wss://data-stream.binance.vision`)
  para actualización instantánea del precio.
- Gráfico de velas con `lightweight-charts` (TradingView, gratuito).
- Índice de Liquidez Institucional (ILI) como métrica compuesta.
- Flujo neto a exchanges vía una API on-chain de pago.
