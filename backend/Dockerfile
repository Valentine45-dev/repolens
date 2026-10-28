FROM python:3.12-slim

# git is needed to clone the repos we analyse. Nothing from those repos is ever executed.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    HF_HOME=/opt/hf

WORKDIR /app
# Default groups minus dev: includes the embed group. torch comes from the CPU-only index
# (pyproject [tool.uv.sources]), so there are no CUDA libraries in the image.
# The uv cache is a build-cache mount, so the downloaded wheels stay out of the image.
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

# The API, and the ingestion jobs it runs in the background, run as this user.
RUN useradd --create-home --uid 1000 repolens \
    && mkdir -p /opt/hf && chown repolens:repolens /opt/hf
USER repolens

# Download the pinned model revision at build time so the demo works offline. Only the files
# this needs are copied first, so changing other app code does not re-download the model.
COPY --chown=repolens:repolens app/__init__.py app/config.py ./app/
COPY --chown=repolens:repolens app/qa/__init__.py app/qa/embed.py ./app/qa/
RUN python -c "from app.qa.embed import get_embedder; e = get_embedder(); \
print('model', e.name, e.revision, 'dim', e.dim, 'max_tokens', e.max_tokens)"
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

COPY --chown=repolens:repolens app ./app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
