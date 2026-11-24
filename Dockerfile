FROM python:3.14-slim@sha256:d712121441a48a45f8452726ccc9fcf7094d8da24ccc2a588bea02fe18d3fb91

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev

EXPOSE 8005

CMD ["uv", "run", "music-assistant-mcp"]
