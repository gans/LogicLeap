.PHONY: up down reset migrate seed test lint

up:
	docker compose up --build

down:
	docker compose down

reset:
	docker compose down -v
	docker compose up --build

migrate:
	docker compose run --rm backend alembic upgrade head

seed:
	docker compose run --rm backend python -m logicleap.seed

test:
	docker compose run --rm backend pytest
	docker compose run --rm frontend npm test

lint:
	docker compose run --rm backend ruff check .
	docker compose run --rm backend mypy src
	docker compose run --rm frontend npm run typecheck

