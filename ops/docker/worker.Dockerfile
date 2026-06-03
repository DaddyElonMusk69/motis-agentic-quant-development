FROM python:3.13-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY apps ./apps
COPY packages ./packages
RUN pip install --no-cache-dir -e .

CMD ["python", "-m", "quant_terminal_worker.service"]
