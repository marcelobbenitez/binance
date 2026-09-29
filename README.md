# Crypto Monitor (BTC / ETH / BNB)

App para monitorear el estado de BTC, ETH y BNB en tiempo real usando datos
públicos de Binance, cruzados con el flujo institucional de los ETF spot
(cuando el activo tiene), el funding rate de futuros, un Índice de Liquidez
Institucional (ILI) y el flujo neto a exchanges (CryptoQuant, opcional), para
estimar si cada uno está en sesgo alcista o bajista.

## Qué muestra

- Precio en vivo (WebSocket de Binance, sin polling) — para BTC, ETH y BNB
  (selector de pestañas en el frontend).
- Gráfico de velas diarias (`lightweight-charts` de TradingView), con la
  última vela actualizándose en vivo por WebSocket.
- Flujo neto diario de los ETF spot (IBIT, FBTC, GBTC, ARKB, ETHA, ETHE,
  etc.), scrapeado de Farside Investors — disponible para **BTC y ETH**.
  BNB no tiene ETF spot aprobado en EE.UU., así que esa capa se muestra
  como "no aplica".
- Funding rate de futuros perpetuos de cada activo.
- Índice de Liquidez Institucional (ILI): score 0-100 del flujo ETF
  normalizado contra su propio rango histórico (ver más abajo).
- Flujo neto a exchanges (CryptoQuant) — **opcional**, requiere tu propia
  API key; sin ella esta capa queda en "sin datos" sin romper nada (ver
  "Activar el flujo neto a exchanges" más abajo).
- Un sesgo consolidado (**ALCISTA** / **BAJISTA** / **NEUTRAL** /
  **DIVERGENCIA**) que cruza las señales anteriores, en vez de mirar
  solo el precio.

## Estructura

```
btc-monitor/
├── app.py                # Backend Flask: sirve index.html + API por activo
├── assets_config.py      # Config de activos soportados (símbolo Binance, slugs, unidad)
├── binance_client.py     # Cliente de los endpoints públicos de Binance (ticker, funding, velas)
├── etf_flows.py          # Scraper + caché del flujo ETF (Farside), por activo
├── exchange_netflow.py   # Cliente del flujo neto a exchanges (CryptoQuant, opcional)
├── ili.py                # Índice de Liquidez Institucional (score + chequeo de máximo de N días)
├── analysis.py           # Lógica de cruce de señales (sesgo alcista/bajista)
├── btc_monitor.py         # Versión CLI (recorre BTC/ETH/BNB con los mismos módulos)
├── index.html             # Frontend (SPA de un solo archivo: tabs, WebSocket, velas)
├── api/index.py           # Entry point para desplegar en Vercel (function serverless)
├── vercel.json
├── requirements.txt
└── .gitignore
```

Agregar un activo nuevo es un solo cambio: sumar una entrada en
`assets_config.py` con su símbolo de Binance y (si tiene) su slug de Farside
y su identificador de CryptoQuant.

## Uso rápido (app completa, recomendado)

```bash
pip install -r requirements.txt
python app.py
```

Abrí `http://127.0.0.1:5000` en el navegador. Elegí la pestaña BTC/ETH/BNB:
el precio y el gráfico de velas se actualizan en vivo por WebSocket, y el
sesgo/ETF/funding/ILI/exchanges se refrescan cada 30 segundos (no cambian
segundo a segundo, así que no hace falta que sean instantáneos).

El backend existe principalmente para scrapear Farside del lado del servidor
(evita problemas de CORS y permite cachear el resultado, ya que el dato es
T+1 y no tiene sentido pedirlo en cada refresco) y para exponer velas/ILI/
exchange-netflow ya calculados.

## Uso solo como CLI

```bash
pip install -r requirements.txt
python btc_monitor.py
```

Imprime el estado de BTC, ETH y BNB uno tras otro, incluyendo ILI y flujo a
exchanges (si está configurado).

## Uso mínimo (solo precio, sin backend)

Si abrís `index.html` directamente como archivo (sin correr `app.py`), el
precio y el gráfico de velas siguen funcionando porque el WebSocket se
conecta directo a `data-stream.binance.vision` desde el navegador (no pasa
por el backend), con fallback a `data-api.binance.vision` por REST si el
WebSocket no conecta. Las tarjetas de sesgo, ETF, ILI y exchanges van a pedir
que levantes el backend, porque dependen de scrapers/APIs del lado del
servidor.

## Activar el flujo neto a exchanges (CryptoQuant)

Esta capa es opcional y viene **apagada por defecto**. Para activarla:

1. Creá tu propia cuenta en [cryptoquant.com](https://cryptoquant.com) y
   generá una API key desde tu panel (la app y quien la generó no pueden
   hacer esto por vos: es tu cuenta, tu plan, tu clave).
2. Configurá la variable de entorno `CRYPTOQUANT_API_KEY` con esa clave:
   - Local: `set CRYPTOQUANT_API_KEY=tu_clave` (PowerShell/cmd) o
     `export CRYPTOQUANT_API_KEY=tu_clave` (bash) antes de correr `python app.py`.
   - Vercel: Project Settings → Environment Variables (o `vercel env add
     CRYPTOQUANT_API_KEY`), pegando el valor vos mismo en el prompt/formulario.
3. Reiniciá el backend. Sin reiniciar el proceso no toma la variable de
   entorno nueva.

Sin la variable configurada, `/api/<asset>/exchange-netflow` devuelve
`{"soportado": false, "razon": "sin_api_key"}` y la señal correspondiente
queda como "sin_datos" — el resto de la app sigue funcionando igual.

### Estado conocido: 403 Forbidden con el plan actual

En pruebas contra producción, `exchange-flows/netflow` devolvió **403
Forbidden** tanto con `exchange=all_exchange` como con `exchange=binance`,
usando la misma API key. Un 403 de CryptoQuant significa key válida pero
plan sin acceso a ese endpoint (a diferencia de un 401 por key inválida), y
que falle igual con un exchange puntual sugiere que es el endpoint
`exchange-flows/netflow` en general el que no está incluido en el plan
actual, no una cuestión del parámetro `exchange` elegido.

`exchange_netflow.py` deja `DEFAULT_EXCHANGE = "binance"` igual (encaja
temáticamente con el resto de la app, que ya gira en torno a datos de
Binance), pero eso no soluciona el 403. Para activar esta señal de verdad
hace falta confirmar en tu cuenta de CryptoQuant qué plan tenés y si incluye
`exchange-flows/netflow`; mientras tanto la app funciona igual con esta capa
en "sin_datos".

## Deploy en Vercel

El repo ya incluye `vercel.json` + `api/index.py` (adaptador serverless de la
misma app Flask). Con la CLI de Vercel:

```bash
npx vercel login
npx vercel --prod
```

O conectando el repo de GitHub desde el dashboard de Vercel para que cada
`git push` a `main` dispare un deploy automático.

## Fuentes de datos

- **Binance REST** (público, sin API key):
  `https://data-api.binance.vision/api/v3/ticker/24hr?symbol=<SYMBOL>` y
  `.../api/v3/klines` para las velas (usa este dominio y no `api.binance.com`:
  es el endpoint pensado para consumo público y no sufre el geo-bloqueo que sí
  afecta a `api.binance.com` en algunos países).
- **Binance WebSocket** (público, sin API key):
  `wss://data-stream.binance.vision/stream?streams=<symbol>@ticker/<symbol>@kline_1d/...`
  — un único socket combinado para los tres activos, con reconexión
  automática (backoff exponencial hasta 30s) si se corta.
- **Funding rate**: `https://fapi.binance.com/fapi/v1/premiumIndex` (público).
  Puede fallar geo-bloqueado desde EE.UU. (Binance no ofrece futuros a
  usuarios de EE.UU.); la app lo maneja como "sin datos".
- **ETF flows**: `https://farside.co.uk/btc/` y `https://farside.co.uk/eth/`
  (scraping de la tabla HTML, única fuente gratuita con el histórico completo
  de flujos diarios, incluyendo el Average/Maximum/Minimum que usa el ILI).
  BNB no tiene equivalente.
- **Flujo neto a exchanges**: `https://api.cryptoquant.com/v1/<btc|eth>/exchange-flows/netflow`
  (requiere `CRYPTOQUANT_API_KEY` propia; ver arriba). BNB no está soportado.
- **Gráfico de velas**: `lightweight-charts` de TradingView, vía CDN
  (`unpkg.com`), gratuito y open-source.

## Cómo se calcula el sesgo

Se cruzan cinco capas de señal (`analysis.py`), iguales para cualquier
activo:

| Señal                    | Alcista                      | Bajista                          |
|--------------------------|-------------------------------|-----------------------------------|
| Precio (24h)             | Variación positiva            | Variación negativa                |
| Flujo ETF (7 días)       | Inflow neto positivo          | Outflow neto                      |
| Funding rate             | Positivo pero no extremo      | Negativo persistente (deleveraging)|
| ILI                      | Score ≥ 60                    | Score ≤ 40                        |
| Flujo neto a exchanges   | Salida neta (sale de exchanges)| Entrada neta (entra a exchanges) |

Si al menos dos señales coinciden, el sesgo se marca ALCISTA o BAJISTA. El
caso más informativo es la **divergencia** entre precio y flujo ETF:

- Precio sube + ETF con outflow → `DIVERGENCIA_AMARILLA` (cautela: el rally
  no está acompañado de entrada institucional).
- Precio baja + ETF con inflow → `DIVERGENCIA_VERDE` (posible acumulación
  institucional pese a la caída de precio).

Para BNB (sin ETF ni CryptoQuant), esas señales quedan en "sin_datos" y el
sesgo se decide solo con precio, funding e ILI (que a su vez depende del ETF,
así que en la práctica queda solo precio + funding).

### Índice de Liquidez Institucional (ILI): versión simplificada

El ILI que describe el resumen original combina flujos de ETF con "liquidez
USD" agregada (algo tipo balance de la Fed / M2), pero esa segunda mitad no
tiene una fuente gratuita y en tiempo real, así que esta app implementa solo
la mitad que sí se puede calcular con datos propios:

```
ili_score = (promedio_diario_flujo_etf_7d − mínimo_histórico) / (máximo_histórico − mínimo_histórico) × 100
```

donde "mínimo/máximo histórico" son el peor outflow y el mejor inflow diario
que Farside registró para ese activo (columnas Minimum/Maximum de su propia
tabla). Es una simplificación deliberada y documentada, no el ILI completo
del resumen original.

Con eso se replica el chequeo de divergencia del resumen original: si el
precio hace un **nuevo máximo de 30 días** (con velas diarias de Binance) pero
el ILI no acompaña, se marca:

- ILI < 60 → `DIVERGENCIA_ILI_AMARILLA` (cautela).
- ILI < 50 → `DIVERGENCIA_ILI_ROJA` (señal de reducir exposición).

Nota: el resumen original habla de "máximo histórico" para la divergencia
roja; acá se usa una ventana de 30 días (la misma que ya se pide para la
divergencia amarilla) en vez de un verdadero all-time-high, porque calcular
un ATH real necesitaría mucho más historial de velas del que tiene sentido
pedir en cada refresco. Queda documentado como aproximación, no como el
criterio exacto del resumen.

### Flujo neto a exchanges: qué significa y qué no

Netflow positivo = entran más monedas a exchanges de las que salen (más
oferta líquida disponible para vender). Netflow negativo = salen más de las
que entran (menos oferta líquida, señal alcista candidata). Pero **un retiro
de exchange no es automáticamente alcista**: puede ser un rebalanceo interno
entre hot/cold wallets del mismo exchange o una transferencia entre
exchanges, no necesariamente una compra que se mueve a cold storage. Por eso
esta señal pesa igual que las demás en el voto, no domina el sesgo por sí
sola.

## Limitaciones prácticas

- Los datos de ETF (y por lo tanto el ILI) son **T+1**: Farside los publica
  con el cierre del día hábil anterior en EE.UU., no en tiempo real. El
  netflow de CryptoQuant también suele publicarse con ese mismo retraso.
- El funding rate puede no estar disponible si `fapi.binance.com` está
  geo-bloqueado desde tu región (por ejemplo, al desplegar en una región de
  EE.UU. en Vercel); la app lo maneja como "sin datos" en vez de romper.
- BNB no tiene flujo ETF, ILI ni flujo a exchanges: el sesgo para ese activo
  se basa solo en precio y funding.
- El flujo a exchanges requiere una API key de CryptoQuant que no viene
  incluida y que puede requerir un plan pago según qué endpoints cubra tu
  cuenta.
- En un entorno serverless (Vercel) el caché en memoria de Farside/CryptoQuant
  se pierde en cada cold start, así que con tráfico bajo cada request puede
  volver a pegarle a la fuente externa en vez de servir desde caché — vigilá
  tu límite de rate si activás CryptoQuant ahí.
- El WebSocket puede no conectar en redes muy restrictivas; la app cae de
  vuelta a polling REST cada 30s mientras tanto y reintenta la conexión con
  backoff exponencial.
- Respetá los límites de peso de la API de Binance (6.000 unidades/minuto).
  El polling de análisis (cada 30s) y el WebSocket (una sola conexión
  persistente) están muy por debajo.

## Posibles mejoras futuras

- Índice de Liquidez Institucional completo, sumando un dato real de
  liquidez USD agregada (por ejemplo, balance de la Fed vía la API de FRED).
- Detección de ATH real (no solo máximo de 30 días) para la divergencia roja
  del ILI, con más historial de velas.
- Caché de Farside/CryptoQuant persistente entre cold starts en serverless
  (por ejemplo, con un KV store), en vez de solo en memoria del proceso.
