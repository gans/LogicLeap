TRIVY_IMAGE := aquasec/trivy:0.70.0@sha256:be1190afcb28352bfddc4ddeb71470835d16462af68d310f9f4bca710961a41e
TRIVY_CACHE_VOLUME := logicleap-trivy-cache
UV_IMAGE := ghcr.io/astral-sh/uv:0.11.28-python3.13-trixie-slim@sha256:08477888ac23d6cfbeb8c7dc6fc70cf297fd38b7bf35522be33ce832750ca242
NODE_IMAGE := node:22-alpine@sha256:16e22a550f3863206a3f701448c45f7912c6896a62de43add43bb9c86130c3e2
BACKEND_RUNTIME_IMAGE := logicleap-backend:runtime
FRONTEND_RUNTIME_IMAGE := logicleap-frontend:runtime

.PHONY: audit-node audit-python build build-images down lint migrate reset scan-config scan-fs scan-images security seed test up verify-locks

build:
	docker compose build
	$(MAKE) build-images

build-images:
	docker build --target runtime --tag $(BACKEND_RUNTIME_IMAGE) --file Dockerfile.backend .
	docker build --target runtime --tag $(FRONTEND_RUNTIME_IMAGE) --file Dockerfile.frontend .

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

audit-python:
	docker compose run --rm backend sh -c 'uv export --frozen --no-dev --no-emit-project --no-hashes --output-file /tmp/requirements.txt && pip-audit --strict --requirement /tmp/requirements.txt'

audit-node:
	docker compose run --rm frontend npm audit --audit-level=high

scan-config:
	docker run --rm --volume $(TRIVY_CACHE_VOLUME):/root/.cache/trivy --volume "$(CURDIR):/workspace:ro" --workdir /workspace $(TRIVY_IMAGE) config --exit-code 1 --severity HIGH,CRITICAL .

scan-fs:
	docker run --rm --volume $(TRIVY_CACHE_VOLUME):/root/.cache/trivy --volume "$(CURDIR):/workspace:ro" --workdir /workspace $(TRIVY_IMAGE) fs --exit-code 1 --severity HIGH,CRITICAL --scanners vuln,secret .

scan-images: build-images
	@set -eu; work="$(CURDIR)/.trivy-work"; trap 'rm -rf "$$work"' EXIT; \
		mkdir -p "$$work"; \
		docker image save --output "$$work/backend.tar" $(BACKEND_RUNTIME_IMAGE); \
		docker image save --output "$$work/frontend.tar" $(FRONTEND_RUNTIME_IMAGE); \
		docker run --rm --volume $(TRIVY_CACHE_VOLUME):/root/.cache/trivy --volume "$$work:/scan:ro" $(TRIVY_IMAGE) image --input /scan/backend.tar --exit-code 1 --severity HIGH,CRITICAL; \
		docker run --rm --volume $(TRIVY_CACHE_VOLUME):/root/.cache/trivy --volume "$$work:/scan:ro" $(TRIVY_IMAGE) image --input /scan/frontend.tar --exit-code 1 --severity HIGH,CRITICAL

verify-locks:
	docker run --rm --volume "$(CURDIR)/backend:/workspace:ro" --workdir /workspace $(UV_IMAGE) uv lock --check
	docker build --target dependencies --file Dockerfile.frontend .

security: verify-locks audit-python audit-node scan-fs scan-config scan-images
