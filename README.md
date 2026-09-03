# rag-demo

Un usuario hace una pregunta, el sistema busca en documentos internos, y un
modelo redacta la respuesta citando de dónde la sacó.

La decisión que gobierna todo el proyecto: **si la búsqueda no encuentra nada
relevante, no se responde.** Un sistema que inventa cuando no encuentra es peor
que uno que dice que no sabe, porque quien pregunta no tiene forma de
distinguir una respuesta buena de una inventada.

## Cómo funciona

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
| `contracts.py` | los dos protocolos que dependen de un modelo |
| `providers.py` | implementación contra Ollama |

## Por qué está separado así

**Solo dos operaciones necesitan un modelo:** convertir texto en vector, y
generar la respuesta. Están aisladas como protocolos en `contracts.py`.

Todo lo demás —trocear, indexar, buscar, umbralizar, armar el prompt, decidir
si abstenerse— es determinista y se prueba sin red, sin claves y sin servidor.
Por eso las 35 pruebas corren en menos de un segundo y funcionan en CI.

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
uv run pytest                     # 35 pruebas, sin red
```

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

## El corpus

Dos documentos sobre complemento Carta Porte y expedientes digitales de
proveedores, escritos para este repositorio. El dominio viene de haber
trabajado en un sistema de logística de transporte, pero el contenido es
propio y no reproduce material de nadie.

## Requisitos

Python 3.13, [uv](https://docs.astral.sh/uv/), y Ollama solo para el modo real.
