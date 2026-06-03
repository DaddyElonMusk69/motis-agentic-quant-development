FROM python:3.13-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY apps ./apps
COPY packages ./packages
RUN pip install --no-cache-dir -e .

CMD ["uvicorn", "quant_terminal_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
