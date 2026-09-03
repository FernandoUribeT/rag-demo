"""Interfaz de línea de comandos.

    uv run rag-demo "¿cuándo se requiere el complemento Carta Porte?"

Requiere Ollama corriendo en local con los modelos descargados:

    ollama pull bge-m3
    ollama pull llama3.1:8b
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .pipeline import BaseDeConocimiento, responder
from .providers import OllamaEmbedder, OllamaLanguageModel

CORPUS = Path(__file__).resolve().parent.parent.parent / "corpus"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rag-demo",
        description="Responde preguntas usando solo los documentos del corpus.",
    )
    parser.add_argument("pregunta", help="la pregunta a responder")
    parser.add_argument("--corpus", type=Path, default=CORPUS)
    parser.add_argument("-k", type=int, default=4, help="fragmentos a recuperar")
    parser.add_argument(
        "--solo-recuperar",
        action="store_true",
        help="muestra los fragmentos recuperados sin invocar al modelo",
    )
    args = parser.parse_args(argv)

    if not args.corpus.is_dir():
        print(f"no existe la carpeta de corpus: {args.corpus}", file=sys.stderr)
        return 2

    base = BaseDeConocimiento(OllamaEmbedder())
    documentos = base.cargar_carpeta(args.corpus)
    print(f"{documentos} documentos · {len(base)} fragmentos indexados\n")

    if args.solo_recuperar:
        coincidencias = base.recuperar(args.pregunta, k=args.k)
        if not coincidencias:
            print("sin coincidencias por encima del umbral")
            return 0
        for c in coincidencias:
            print(f"[{c.fragmento.id}]  similitud {c.similitud:.3f}")
            print(f"  {c.fragmento.texto[:160]}...\n")
        return 0

    respuesta = responder(
        args.pregunta, base, OllamaLanguageModel(), k=args.k
    )
    print(respuesta.texto)

    if respuesta.fuentes:
        print("\nfuentes:")
        for c in respuesta.fuentes:
            print(f"  [{c.fragmento.id}]  similitud {c.similitud:.3f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
