# syntax=docker/dockerfile:1.7

# --- build stage ---
FROM python:3.13-slim AS build
WORKDIR /src

COPY pyproject.toml ./
COPY nas_md/ ./nas_md/

# --- runtime stage ---
FROM python:3.13-slim AS runtime
RUN groupadd -g 1000 app && useradd -D -u 1000 -g app app

WORKDIR /app

COPY --from=build /src/nas_md/ /app/nas_md/
COPY --from=build /src/pyproject.toml /app/pyproject.toml
COPY web/ /app/web/

RUN mkdir -p /app/storage /app/tokens && chown -R app:app /app
# tokens: Telegram Bot 令牌存储（Web 模式未使用）
VOLUME ["/app/storage", "/app/tokens"]

USER app

EXPOSE 8080

ENV PYTHONPATH=/app
ENV WEB_ROOT=/app/web
ENV STORAGE_DIR=/app/storage
# tokens: Telegram Bot 令牌存储（Web 模式未使用）
ENV TOKENS_DIR=/app/tokens
ENV MOUNT_DIRS=""
ENV WEB_PORT=8080

ENTRYPOINT ["python3", "-m", "nas_md.cli"]
CMD ["web"]
