# Imagen con uv preinstalado: evita un paso de instalación y fija la versión
# del gestor, para que la construcción no cambie porque uv publicó otra.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Las dependencias se copian e instalan ANTES que el código fuente.
# Docker cachea cada capa: así un cambio en el código no vuelve a descargar
# e instalar todo, que es el 90% del tiempo de construcción.
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --extra servicios

COPY src/ ./src/
COPY corpus/ ./corpus/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --extra servicios

# Usuario sin privilegios: si alguien logra ejecutar algo dentro del
# contenedor, no lo hace como root.
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

ENV PATH="/app/.venv/bin:$PATH"

CMD ["rag-demo", "--help"]
