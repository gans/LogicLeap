# LogicLeap

LogicLeap is a human-controlled SDLC context and coordination system.

## Safe local development

Docker Compose is the primary execution path. Dependency installation happens
inside pinned container images; no host Python or Node installation is required.
Start PostgreSQL, FastAPI, the Streamable HTTP MCP server, and React/Vite with:

```sh
docker compose up --build
```

- UI: http://localhost:5173
- API: http://localhost:8000
- API documentation: http://localhost:8000/docs
- MCP Streamable HTTP endpoint: http://localhost:8001/mcp

The application ports bind only to `127.0.0.1`. PostgreSQL has no host port and
is reachable only over the internal Compose database network. Backend and MCP
wait for PostgreSQL health; backend applies Alembic migrations before FastAPI
starts. Application containers run without root, Linux capabilities, or privilege
escalation.

The committed database username and password are explicitly local-development
defaults. Override them in an ignored `.env` copied from `.env.example` when
desired. This Compose file is not production configuration: any non-development
deployment must provide unique credentials and must not rely on these defaults.

Never mount your home directory, the Docker socket, an SSH agent, or cloud
credential directories into these containers. Do not pass company credentials,
tokens, private keys, or cloud credentials as build arguments.

Useful commands:

```sh
docker compose up --build
docker compose run --rm backend pytest
docker compose run --rm backend ruff check .
docker compose run --rm backend mypy src
docker compose run --rm frontend npm test
docker compose run --rm frontend npm run typecheck
docker compose run --rm frontend npm run build
docker compose config
docker compose build --no-cache
docker compose down
docker compose down -v
```

`docker compose down -v` permanently removes this project's local PostgreSQL
volume. The Make shortcuts are `make build`, `make up`, `make down`, `make reset`,
`make migrate`, `make seed`, `make test`, and `make lint`.

Seed the running database with a migration epic, an architect, an analysis agent,
and three representative tasks:

```sh
make seed
```

The seed is idempotent. PostgreSQL data persists in the named `postgres_data`
volume.

## Reproducible dependencies

Python runtime and development dependencies are resolved in `backend/uv.lock`.
Runtime images use `uv sync --frozen --no-dev` and install LogicLeap
non-editably; test, lint, and audit packages exist only in the development stage.
Frontend direct dependencies are exact versions and `frontend/package-lock.json`
is installed with `npm ci --ignore-scripts`. The current dependency graph does
not require lifecycle scripts; the optional platform package `fsevents` declares
an install script but a clean install, tests, and production build succeed with
scripts disabled.

Verify both committed locks without changing them:

```sh
make verify-locks
```

To update Python dependencies, edit compatible constraints in
`backend/pyproject.toml`, then regenerate and validate the lock with the same
digest-pinned uv image used by the Makefile:

```sh
docker run --rm -v "$PWD/backend:/workspace" -w /workspace \
  ghcr.io/astral-sh/uv:0.11.28-python3.13-trixie-slim@sha256:08477888ac23d6cfbeb8c7dc6fc70cf297fd38b7bf35522be33ce832750ca242 \
  uv lock
make verify-locks
```

To update frontend dependencies, edit `frontend/package.json` to exact reviewed
versions and update the lock in a one-off pinned Node container. This is a lock
maintenance operation, not an image build or CI install:

```sh
docker run --rm -v "$PWD/frontend:/app" -w /app \
  node:22-alpine@sha256:16e22a550f3863206a3f701448c45f7912c6896a62de43add43bb9c86130c3e2 \
  npm update --package-lock-only --ignore-scripts
make verify-locks
```

Review the lock diff and run all tests and audits before committing. Dependabot
proposes weekly Python, npm, Docker, and GitHub Actions updates. Non-major updates
may be grouped; major upgrades remain separate and are never auto-merged.

## Base-image updates

All Python, uv, Node, PostgreSQL, nginx, and Dockerfile-frontend image references
retain a readable tag and pin an immutable manifest digest. To update one safely:

1. Select a reviewed official tag and inspect it with
   `docker buildx imagetools inspect <image>:<tag>`.
2. Copy the reported multi-platform `Digest` exactly; never invent a digest.
3. Update every matching reference while retaining the readable tag.
4. Run `docker compose build --no-cache`, `make test`, `make lint`, and
   `make security`.
5. Review the image and vulnerability scan changes before committing.

Dependabot also proposes Docker tag and digest updates explicitly.

## Security checks

The local security suite uses digest-pinned scanner containers and committed
locks:

```sh
make audit-python
make audit-node
make scan-config
make scan-images
make security
```

`make security` also verifies locks and scans the repository filesystem. Python
uses `pip-audit` against an exported frozen runtime dependency set. Node uses
`npm audit --audit-level=high`. Trivy scans repository files, Docker
configuration, and tar exports of both final runtime images; it does not mount
the Docker socket. High and critical findings fail by default.

There is currently no Trivy ignore file. If an exception becomes unavoidable,
it must name only the specific CVE and affected package and document the
justification, compensating control, owner, and review/expiration date. Broad
wildcards are prohibited. Never use `npm audit fix --force` as an automated fix.

Inspect the effective local configuration before startup:

```sh
docker compose config
```

Rebuild every layer and remove all local project resources with:

```sh
docker compose build --no-cache
docker compose down -v
```

## Design guarantees

- UUID4 primary keys and timezone-aware PostgreSQL timestamps
- dedicated epic and task architect foreign keys
- optimistic task versions on meaningful child mutations
- append-only aggregate events ordered by aggregate sequence
- intent-specific APIs and MCP tools; no hard delete, generic update, SQL tool,
  or arbitrary query surface
- centralized transition and readiness policies shared by every adapter
