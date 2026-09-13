.PHONY: db-up db-health db-init app-up app-health test quality eval

db-up:
	docker-compose up -d --wait postgres

db-health:
	docker-compose exec -T postgres pg_isready -U $${POSTGRES_USER:-shoppulse} -d $${POSTGRES_DB:-shoppulse}

db-init: db-up
	uv run shoppulse-wait-db --timeout 60
	uv run alembic upgrade head

test:
	uv run pytest -q

quality:
	uv run shoppulse-quality

app-up:
	docker-compose up --build --wait

app-health:
	curl --fail http://localhost:8000/health/ready

eval:
	uv run shoppulse-eval --output-dir reports/phase3
