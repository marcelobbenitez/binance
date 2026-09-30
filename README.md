# Crypto Monitor (BTC / ETH / BNB)

App para monitorear el estado de BTC, ETH y BNB en tiempo real usando datos
públicos de Binance, cruzados con el flujo institucional de los ETF spot
(cuando el activo tiene), el funding rate de futuros y un Índice de Liquidez
Institucional (ILI), para estimar si cada uno está en sesgo alcista o
bajista, un rango estadístico de cuánto suele moverse el precio en 7, 14 y
30 días (volatilidad, no una predicción de precio), y un **backtesting**
que muestra qué porcentaje de las veces subió o bajó el precio, en el
pasado, cuando el mercado tuvo el mismo sesgo que tiene ahora.

## Qué muestra

- Precio en vivo (WebSocket de Binance, sin polling) — para BTC, ETH y BNB
  (selector de pestañas en el frontend).
- Gráfico de velas (`lightweight-charts` de TradingView) con selector de
  intervalo **1H / 4H / 1D**, volumen debajo de las velas, y la última vela
  actualizándose en vivo por WebSocket (se resuscribe automáticamente al
  cambiar de intervalo). En 1D, además, marcadores de flujo ETF directo sobre
  las velas (flecha verde/roja con el monto) para ver precio + flujo
  institucional en el mismo gráfico.
- Flujo neto diario de los ETF spot (IBIT, FBTC, GBTC, ARKB, ETHA, ETHE,
  etc.), scrapeado de Farside Investors — disponible para **BTC y ETH**.
  BNB no tiene ETF spot aprobado en EE.UU., así que esa capa se muestra
  como "no aplica".
- Funding rate de futuros perpetuos de cada activo.
- Índice de Liquidez Institucional (ILI): score 0-100 del flujo ETF
  normalizado contra su propio rango histórico (ver más abajo).
- Un sesgo consolidado (**ALCISTA** / **BAJISTA** / **NEUTRAL** /
  **DIVERGENCIA**) que cruza las señales anteriores, en vez de mirar
  solo el precio.
- **Rango de movimiento esperado** a 7, 14 y 30 días, basado en volatilidad
  implícita de opciones (Deribit, BTC/ETH) o volatilidad histórica realizada
  como fallback (BNB). Es una magnitud estadística de "cuánto suele moverse
  el precio", independiente y complementaria al sesgo — no una predicción de
  precio ni de dirección (ver más abajo).
- **Backtesting del sesgo actual**: para cada sesgo posible, qué porcentaje
  de las veces subió o bajó el precio 7/14/30 días después, calculado sobre
  el histórico real desde que existen los ETF (2024 para BTC, 2024 para ETH).
  Es una frecuencia empírica con su tamaño de muestra a la vista, no una
  predicción (ver más abajo).

## Estructura

```
btc-monitor/
├── app.py              # Backend Flask: sirve index.html + API por activo
├── assets_config.py    # Config de activos soportados (símbolo Binance, slugs, unidad)
├── binance_client.py   # Cliente de los endpoints públicos de Binance (ticker, funding, velas)
├── etf_flows.py        # Scraper + caché del flujo ETF (Farside), por activo
├── ili.py              # Índice de Liquidez Institucional (score + chequeo de máximo de N días)
├── volatility.py       # Rango de movimiento esperado (volatilidad implícita/histórica)
├── backtest.py         # Frecuencia histórica de subida/bajada por sesgo (backtesting)
├── analysis.py         # Lógica de cruce de señales (sesgo alcista/bajista)
├── btc_monitor.py       # Versión CLI (recorre BTC/ETH/BNB con los mismos módulos)
├── index.html           # Frontend (SPA de un solo archivo: tabs, WebSocket, velas)
├── api/index.py         # Entry point para desplegar en Vercel (function serverless)
├── vercel.json
├── requirements.txt
└── .gitignore
```

Agregar un activo nuevo es un solo cambio: sumar una entrada en
`assets_config.py` con su símbolo de Binance y (si tiene) su slug de Farside.

## Uso rápido (app completa, recomendado)

```bash
pip install -r requirements.txt
python app.py
```

Abrí `http://127.0.0.1:5000` en el navegador. Elegí la pestaña BTC/ETH/BNB:
el precio y el gráfico de velas se actualizan en vivo por WebSocket, y el
sesgo/ETF/funding/ILI se refrescan cada 30 segundos (no cambian segundo a
segundo, así que no hace falta que sean instantáneos).

El backend existe principalmente para scrapear Farside del lado del servidor
(evita problemas de CORS y permite cachear el resultado, ya que el dato es
T+1 y no tiene sentido pedirlo en cada refresco) y para exponer velas/ILI/
backtest ya calculados. La tarjeta de backtesting puede tardar unos segundos
la primera vez que abrís cada activo (recorre ~1-2 años de historia); una vez
calculado queda cacheado 12 horas.

## Uso solo como CLI

```bash
pip install -r requirements.txt
python btc_monitor.py
```

Imprime el estado de BTC, ETH y BNB uno tras otro, incluyendo el ILI y el
backtesting del sesgo actual (esto último tarda unos segundos por activo).

## Uso mínimo (solo precio, sin backend)

Si abrís `index.html` directamente como archivo (sin correr `app.py`), el
precio y el gráfico de velas siguen funcionando porque el WebSocket se
conecta directo a `data-stream.binance.vision` desde el navegador (no pasa
por el backend), con fallback a `data-api.binance.vision` por REST si el
WebSocket no conecta. Las tarjetas de sesgo, ETF e ILI van a pedir que
levantes el backend, porque dependen del scraper de Farside.

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
- **Gráfico de velas**: `lightweight-charts` de TradingView, vía CDN
  (`unpkg.com`), gratuito y open-source.
- **Volatilidad implícita**: `https://www.deribit.com/api/v2/public/get_volatility_index_data`
  (índice DVOL, público, sin API key), solo BTC y ETH. BNB (y cualquier falla
  de Deribit) usa volatilidad histórica calculada de las velas de Binance.
- **Backtesting**: histórico completo de Farside (`farside.co.uk/bitcoin-etf-flow-all-data/`
  y `.../ethereum-etf-flow-all-data/`, ~700 y ~560 días respectivamente, desde
  el lanzamiento de cada ETF) + historial de funding rate de Binance
  (`https://fapi.binance.com/fapi/v1/fundingRate`, paginado) + velas diarias.

## Cómo se calcula el sesgo

Se cruzan cuatro capas de señal (`analysis.py`), iguales para cualquier
activo:

| Señal              | Alcista                      | Bajista                          |
|--------------------|-------------------------------|-----------------------------------|
| Precio (24h)       | Variación positiva            | Variación negativa                |
| Flujo ETF (7 días) | Inflow neto positivo          | Outflow neto                      |
| Funding rate       | Positivo pero no extremo      | Negativo persistente (deleveraging)|
| ILI                | Score ≥ 60                    | Score ≤ 40                        |

Si al menos dos señales coinciden, el sesgo se marca ALCISTA o BAJISTA. El
caso más informativo es la **divergencia** entre precio y flujo ETF:

- Precio sube + ETF con outflow → `DIVERGENCIA_AMARILLA` (cautela: el rally
  no está acompañado de entrada institucional).
- Precio baja + ETF con inflow → `DIVERGENCIA_VERDE` (posible acumulación
  institucional pese a la caída de precio).

Para BNB (sin ETF), la señal ETF e ILI quedan en "sin_datos" y el sesgo se
decide solo con precio + funding.

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

### Rango de movimiento esperado: magnitud, no dirección

El sesgo (ALCISTA/BAJISTA/etc.) responde *hacia dónde* podría inclinarse el
mercado. Es una pregunta distinta a *cuánto* suele moverse el precio en
cierto plazo — para eso, `volatility.py` calcula un rango estadístico
independiente, simétrico alrededor del precio actual:

```
movimiento_horizonte = precio × (volatilidad_anual / 100) × sqrt(dias / 365)
rango = [precio − movimiento_horizonte, precio + movimiento_horizonte]
```

La volatilidad usada es, en orden de preferencia:

1. **Implícita** (BTC/ETH): el índice DVOL de Deribit, que resume lo que el
   propio mercado de opciones está pagando por cobertura — a diferencia de
   mirar el pasado, esto es una expectativa *hacia adelante* real del
   mercado, la referencia más legítima que existe para este propósito.
2. **Histórica realizada** (BNB, o si Deribit falla): desvío estándar de los
   retornos diarios logarítmicos de los últimos 30 días de velas de Binance,
   anualizado. Es un fallback más débil porque describe el pasado, no lo que
   el mercado espera.

El rango es de **±1 desvío estándar**, que bajo el supuesto (aproximado, es
el estándar en pricing de opciones) de retornos lognormales correspondería a
~68% de probabilidad de que el precio quede dentro. En la práctica, los
retornos de cripto tienen colas más pesadas que una distribución normal
(movimientos extremos más frecuentes de lo que esa aproximación predice), así
que la probabilidad real de quedar dentro del rango suele ser algo menor a
ese 68% teórico. Por eso se presenta como "rango típico de movimiento", no
como un límite garantizado ni como un precio objetivo — combinado con el
sesgo da dirección + magnitud, pero sigue sin ser una predicción puntual de
precio ni de fecha.

### Backtesting: probabilidad empírica, no una predicción

Además del sesgo y del rango de movimiento, la app responde una tercera
pregunta: *cuando el mercado se vio así antes, qué pasó realmente*.
`backtest.py` reconstruye, día por día desde que existe cada ETF, el mismo
sesgo que calcula `analizar_estado()` en vivo — usando solo datos
disponibles hasta ese día, sin mirar al futuro — y lo compara con el retorno
real del precio 7/14/30 días después. El resultado es una frecuencia
empírica real, con su tamaño de muestra (N) siempre a la vista:

> "Cuando el sesgo fue ALCISTA en el pasado (N=572, desde 2024-01-14),
> el precio subió 7 días después el 53% de las veces."

Esto es deliberadamente distinto de convertir el conteo de señales del
sesgo en un porcentaje inventado (por ejemplo, "3 de 4 señales alcistas =
75% de probabilidad"): ese número no significaría nada, porque nunca se
validó contra lo que pasó en la realidad. La frecuencia del backtesting sí
está anclada a datos reales — pero eso no la vuelve una garantía.

**Limitaciones honestas de este backtesting** (mostradas también en la propia
tarjeta de la app):

- **Muestra chica**: los ETF de BTC/ETH existen desde 2024, así que hay a lo
  sumo ~700-1000 días de historia. Categorías de sesgo poco frecuentes
  (`DIVERGENCIA_VERDE`, `NEUTRAL`) pueden tener N muy bajo (a veces menos de
  30-50 casos) — la app lo marca explícitamente como "muestra chica, tomalo
  con pinzas".
- **Ventanas solapadas**: el retorno a 7 días del lunes y el del martes
  comparten casi los mismos precios, así que no son observaciones
  estadísticamente independientes entre sí. El N es "días de la muestra", no
  "eventos independientes" — esto es una frecuencia descriptiva, no un test
  de hipótesis con significancia estadística real.
- **El pasado no garantiza el futuro**: que un patrón se haya repetido en
  este período específico (un mercado alcista estructural post-halving) no
  significa que se vaya a repetir en cualquier régimen de mercado futuro.
- **BNB** no tiene ETF, así que su backtest usa solo precio + funding (menos
  señales, categorías de sesgo más limitadas).
- El cálculo completo tarda varios segundos (recorre toda la historia), así
  que se cachea 12 horas por activo; en un entorno serverless (Vercel) esa
  caché se pierde en cada cold start, igual que la de Farside/ETF.

### Por qué no se incluye el flujo neto a exchanges (retiros/depósitos)

Es una de las señales del análisis original. Se llegó a implementar vía
CryptoQuant (`exchange-flows/netflow`), pero el endpoint devolvía **403
Forbidden** tanto para el agregado de todos los exchanges como para un
exchange puntual (Binance) — el plan de la cuenta usada no cubre ese
endpoint. En vez de dejar en la app una capa configurada que nunca trae
datos, se sacó por completo. Además, aunque se consiguiera el dato, un
retiro de exchange no es automáticamente alcista: puede ser un rebalanceo
interno entre hot/cold wallets, no necesariamente acumulación.

Si en el futuro se consigue una fuente confiable (CryptoQuant con un plan que
cubra el endpoint, Glassnode, u otra), se puede reintroducir siguiendo el
mismo patrón que `etf_flows.py`: un módulo propio, cacheado, que se conecta a
`analizar_estado()` en `analysis.py` como una señal más, degradando a
"sin_datos" si no está disponible.

## Limitaciones prácticas

- Los datos de ETF (y por lo tanto el ILI) son **T+1**: Farside los publica
  con el cierre del día hábil anterior en EE.UU., no en tiempo real.
- El funding rate puede no estar disponible si `fapi.binance.com` está
  geo-bloqueado desde tu región (por ejemplo, al desplegar en una región de
  EE.UU. en Vercel); la app lo maneja como "sin datos" en vez de romper.
- BNB no tiene flujo ETF ni ILI: el sesgo para ese activo se basa solo en
  precio y funding.
- El rango de movimiento esperado asume (aproximadamente) retornos
  lognormales; en cripto la probabilidad real de quedar dentro del rango
  suele ser algo menor al ~68% teórico por las colas más pesadas que una
  normal. No es una predicción de precio ni de fecha, es una referencia de
  magnitud típica de movimiento.
- El backtesting tiene muestra chica (los ETF existen desde 2024) y usa
  ventanas de retorno solapadas (no independientes entre sí); es una
  frecuencia histórica real, no una garantía de lo que va a pasar. La
  primera carga por activo puede tardar varios segundos.
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
- Flujo neto a exchanges vía una fuente on-chain con un plan que efectivamente
  cubra el endpoint (ver nota arriba).
- Backtesting con ventanas no solapadas (o block bootstrap) para tener una
  muestra estadísticamente más rigurosa, a costa de un N mucho menor.
- Caché del backtest persistente entre cold starts en serverless (hoy se
  recalcula desde cero si el proceso se reinicia), por ejemplo con un KV store.
