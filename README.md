# LogicLeap

LogicLeap is a human-controlled SDLC context and coordination system.

## Local development

Docker Compose is the primary execution path. Start PostgreSQL, the FastAPI API,
the Streamable HTTP MCP server, and the React/Vite UI with:

```sh
docker compose up --build
```

- UI: http://localhost:5173
- API: http://localhost:8000
- API documentation: http://localhost:8000/docs
- MCP Streamable HTTP endpoint: http://localhost:8001/mcp

The backend waits for PostgreSQL and applies Alembic migrations before starting.

```sh
docker compose run --rm backend pytest
docker compose run --rm backend ruff check .
docker compose run --rm backend mypy src
docker compose run --rm frontend npm test
docker compose run --rm frontend npm run typecheck
docker compose down
docker compose down -v
```

The equivalent shortcuts are `make up`, `make down`, `make reset`, `make migrate`,
`make seed`, `make test`, and `make lint`.
