FROM ghcr.io/astral-sh/uv:0.13.7 AS uv
FROM python:3.13-slim

COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never
WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project
COPY src ./src
RUN uv sync --locked --no-editable

RUN groupadd --gid 10001 collector \
    && useradd --create-home --uid 10001 --gid collector collector \
    && install -d -o collector -g collector /data
USER collector

ENTRYPOINT ["uv", "run", "--no-sync", "referral-collector"]
CMD ["health"]
