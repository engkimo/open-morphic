PORT ?= 8001

.PHONY: test test-unit test-integration lint serve docker-up docker-prod clean

test: test-unit test-integration

test-unit:
	uv run --extra dev pytest tests/unit/ -v

test-integration:
	uv run --extra dev pytest tests/integration/ -v

lint:
	uv run --extra dev ruff check .

serve:
	uv run uvicorn interface.api.main:app --host 0.0.0.0 --port $(PORT) --reload

docker-up:
	docker compose up -d

docker-prod:
	docker compose -f docker-compose.prod.yml up -d --build

ui-dev:
	cd ui && npm run dev

ui-build:
	cd ui && npm run build

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
