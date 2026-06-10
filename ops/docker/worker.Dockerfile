FROM python:3.13-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY apps ./apps
COPY packages ./packages
RUN pip install --no-cache-dir -e .

CMD ["sh", "-c", "celery -A quant_terminal_worker.celery_app:celery_app worker --loglevel=INFO --concurrency=${CELERY_CONCURRENCY:-4} -Q ${CELERY_QUEUES:-market_data,signal_generation,research,execution,default}"]
