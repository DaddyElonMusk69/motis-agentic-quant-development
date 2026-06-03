.PHONY: dev-api dev-worker dev-web test compose-up compose-down

PYTHONPATH := packages/strategy_sdk/src:apps/api/src:apps/worker/src

dev-api:
	PYTHONPATH=$(PYTHONPATH) uvicorn quant_terminal_api.main:app --reload --host 0.0.0.0 --port 8000

dev-worker:
	PYTHONPATH=$(PYTHONPATH) python3 -m quant_terminal_worker.service

dev-web:
	npm --workspace apps/web run dev -- --host 0.0.0.0

test:
	PYTHONPATH=$(PYTHONPATH) python3 -m pytest tests -q

compose-up:
	docker compose --env-file .env -f ops/docker-compose.yml up --build

compose-down:
	docker compose --env-file .env -f ops/docker-compose.yml down
