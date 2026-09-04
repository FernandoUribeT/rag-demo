# rag-demo

[![tests](https://github.com/FernandoUribeT/rag-demo/actions/workflows/tests.yml/badge.svg)](https://github.com/FernandoUribeT/rag-demo/actions/workflows/tests.yml)

Un usuario hace una pregunta, el sistema busca en documentos internos, y un
modelo redacta la respuesta citando de dónde la sacó.

La decisión que gobierna todo el proyecto: **si la búsqueda no encuentra nada
relevante, no se responde.** Un sistema que inventa cuando no encuentra es peor
que uno que dice que no sabe, porque quien pregunta no tiene forma de
distinguir una respuesta buena de una inventada.

## Cómo funciona

Ingesta de un documento:

```
subir ──► MinIO (guarda el archivo) ──► RabbitMQ (encola el indexado)
                                              │
                                           worker
                                              │
                              trocear ──► vectorizar ──► índice
                                              │
                                        Redis (caché)
```

Consulta:

```
pregunta ──► vector ──► búsqueda por similitud ──► ¿supera el umbral?
                                                      │
                                    no ◄──────────────┴──────────────► sí
                                     │                                  │
                          "no encontré nada"              contexto + pregunta
                        (no se llama al modelo)                        │
                                                                    modelo
                                                                       │
                                                          respuesta con fuentes
```

| Módulo | Responsabilidad |
|---|---|
| `chunking.py` | parte documentos en fragmentos recuperables sin cortar párrafos |
| `store.py` | índice vectorial en memoria, similitud coseno, umbral |
| `pipeline.py` | recuperación, armado del prompt y regla de abstención |
| `cache.py` | caché de vectores; decorador sobre cualquier `Embedder` |
| `ingesta.py` | aceptar documento, encolar, procesar en el worker |
| `storage.py` | almacén de objetos para el documento original |
| `creditos.py` | saldo de créditos, otorgamiento idempotente |
| `pagos.py` | frontera con Stripe: sesión de pago y verificación de webhook |
| `contracts.py` | los protocolos que dependen de un modelo |
| `api.py` | API HTTP con FastAPI: consultar y subir documentos |
| `providers.py`, `cola_rabbitmq.py` | adaptadores: Ollama, RabbitMQ |
| `web/` | interfaz en Angular que consume la API |

## Por qué ingesta asíncrona

Trocear y vectorizar un documento largo tarda. Hacerlo dentro de la petición
deja al usuario esperando y, si el proceso muere a la mitad, el documento queda
indexado por partes sin que nadie se entere.

`aceptar()` guarda el archivo y encola el trabajo: responde de inmediato.
`procesar()` lo ejecuta un worker aparte. La carga es rápida, el trabajo pesado
es reintentable, y se escala el indexado agregando workers sin tocar la API.

El mensaje lleva la **clave** del objeto, nunca el documento. Un documento
dentro de la cola la convierte en un almacén improvisado, con sus límites de
tamaño y sin forma de releerlo después.

El procesamiento es idempotente porque la clave incluye el hash del contenido.
Eso importa: una cola garantiza *al menos una* entrega, no exactamente una.

## Por qué cachear los vectores

Vectorizar es la operación cara: cada llamada cruza la red hacia el modelo. Y
se repite más de lo que parece — al reindexar, la mayoría de los fragmentos no
cambió, y la misma pregunta llega varias veces.

La clave de caché incluye el nombre del modelo. Omitirlo es el error clásico
que, tras cambiar de modelo, sigue devolviendo vectores del anterior —
incomparables con los nuevos, y sin ningún síntoma visible.

## Cobro por créditos

Indexar cuesta cómputo, así que se cobra por documento indexado. Tres reglas
gobiernan esa parte, y las tres son de seguridad:

**El precio lo pone el servidor.** El comprador elige una clave de paquete, no
un monto. Si el navegador mandara el precio, cualquiera edita la petición y
compra doscientos créditos por un centavo.

**Los créditos se otorgan en el webhook, no en la página de éxito.** Esa URL la
puede abrir cualquiera a mano sin haber pagado. El webhook lo manda Stripe
cuando el cobro se confirmó.

**Un webhook sin firma válida se rechaza.** El endpoint es público: cualquiera
puede mandarle un POST diciendo "este cliente pagó". La firma es lo único que
distingue a Stripe de un impostor. Se verifica sobre los bytes crudos del
cuerpo, porque convertir a JSON y volver a serializar cambia el contenido y
rompe la comprobación.

Y una cuarta, de correctitud: **otorgar es idempotente.** Stripe reintenta un
webhook hasta recibir 2xx y puede entregar el mismo evento más de una vez por
diseño. Sin esa guarda, un reintento regala créditos: se paga una vez y se
recibe dos. La clave de idempotencia es el id del evento.

El cobro ocurre **antes** de encolar el documento. Al revés, un saldo
insuficiente dejaría el trabajo en la cola y el worker indexaría algo que nadie
pagó.

## Por qué está separado así

**Solo dos operaciones necesitan un modelo:** convertir texto en vector, y
generar la respuesta. Están aisladas como protocolos en `contracts.py`.

Todo lo demás —trocear, indexar, buscar, umbralizar, armar el prompt, decidir
si abstenerse— es determinista y se prueba sin red, sin claves y sin servidor.
Por eso las 115 pruebas corren en menos de un segundo y funcionan en CI.

Una suite que necesita un modelo real no corre en CI, y una suite que no corre
en CI termina no corriendo nunca.

El mismo corte permite cambiar de proveedor —OpenAI, Gemini, Claude— escribiendo
una clase con dos métodos, sin tocar la lógica de recuperación.

## Decisiones que vale la pena explicar

**Umbral de similitud, y devolver menos de `k`.** Pedir los 4 fragmentos más
parecidos siempre devuelve 4, aunque ninguno venga al caso. Rellenar hasta `k`
con lo mejor disponible es la causa más común de que un sistema RAG conteste
con seguridad usando contexto irrelevante. Aquí, lo que no supera el umbral no
entra.

**No se invoca al modelo cuando se abstiene.** Además de ser lo correcto,
ahorra la llamada más cara del flujo. Hay una prueba que usa un modelo que
falla si alguien lo llama, para que esa garantía no se pierda en un refactor.

**Ollama en local.** El corpus nunca sale de la máquina. Para documentos
internos de una empresa —contratos, procedimientos, expedientes— esa
diferencia suele ser el requisito que decide, no una preferencia técnica.

**numpy en lugar de una base vectorial.** Para decenas o cientos de fragmentos
una matriz de numpy es más rápida que cualquier servicio, y deja a la vista la
operación que una librería escondería. Cuando el corpus deje de caber en
memoria, `store.py` es la única pieza que hay que cambiar.

**Sin LangChain.** El flujo completo son unas 200 líneas legibles. Un framework
aquí agregaría dependencias y capas sin quitar trabajo.

## Ejecutar

```bash
uv sync --dev
uv run pytest                     # 115 pruebas, sin red ni servicios
```

Con todas las dependencias, en contenedores:

```bash
docker compose up -d              # Redis, RabbitMQ, MinIO y la app
docker compose run --rm app rag-demo "¿cuándo se requiere Carta Porte?"
```

Las consolas web quedan en `localhost:15672` (RabbitMQ) y `localhost:9001`
(MinIO), útiles para ver la cola y los objetos mientras se depura.

Para usarlo de verdad hace falta Ollama en local:

```bash
ollama pull bge-m3
ollama pull llama3.1:8b

uv run rag-demo "¿cuándo se requiere el complemento Carta Porte?"
uv run rag-demo "¿qué documentos integran un expediente?" --solo-recuperar
```

`--solo-recuperar` muestra qué fragmentos recuperó y con qué similitud, sin
invocar al modelo. Es la forma de depurar la calidad de la búsqueda por
separado de la calidad de la redacción: cuando la respuesta sale mal, primero
hay que saber cuál de las dos etapas falló.

## La interfaz

Una aplicación de Angular en `web/`: se escribe la pregunta, se muestra la
respuesta y debajo las fuentes con su similitud.

Cuando el sistema se abstiene, la interfaz lo dice explícitamente en lugar de
mostrar el mensaje a secas. Un "no encontré nada" sin explicación se lee como
si el sistema hubiera fallado; con la nota de que ningún fragmento superó el
umbral, se entiende que decidió no responder.

Toda la comunicación con el backend vive en `rag.service.ts`, y el detalle
técnico de un error se queda en la consola: al usuario le llega un mensaje
legible, no un stack trace del servidor.

```bash
cd web
npm ci
npx ng test --watch=false   # 20 pruebas
npx ng serve                # http://localhost:4200
```

Las 20 pruebas corren sin backend: `HttpTestingController` intercepta las
peticiones en las del servicio, y el componente recibe un doble de `RagService`
en las suyas.

## Cómo verificarlo de punta a punta

Las 118 pruebas cubren la lógica sin red. Lo que no pueden cubrir es que el
sistema real, contra Stripe real, se comporte como se espera — y ahí estaba el
único defecto que llegó a producirse: la librería de Stripe devuelve objetos
que se parecen a un diccionario pero no lo son, y el doble de prueba, construido
con `json.loads`, era más permisivo que la realidad. Las pruebas seguían en
verde con el webhook roto.

Por eso existe `verificar.sh`. Con el servidor y `stripe listen` corriendo:

```bash
./verificar.sh
```

Comprueba solo lo que puede comprobar solo —salud, saldo inicial, rechazo sin
créditos, firma inválida, paquete inventado— y para lo que necesita un pago
real te entrega la URL y el identificador de cliente de esa corrida.

Las dos comprobaciones manuales que importan:

**Después de pagar**, el saldo debe subir. **Reenviando el mismo evento**, el
saldo NO debe volver a subir: Stripe reintenta hasta recibir 2xx y puede
repetir un evento por diseño.

Y una tercera que se hace a mano en el navegador: abrir la URL de éxito sin
haber pagado. El saldo no debe cambiar. Otorgar el producto en esa página es el
defecto clásico de las integraciones de pago, porque cualquiera puede
navegar ahí.

## El corpus

Dos documentos sobre complemento Carta Porte y expedientes digitales de
proveedores, escritos para este repositorio. El dominio viene de haber
trabajado en un sistema de logística de transporte, pero el contenido es
propio y no reproduce material de nadie.

## Requisitos

Python 3.13 y [uv](https://docs.astral.sh/uv/). Ollama solo para el modo real; Docker solo si se quieren levantar Redis, RabbitMQ y MinIO.
