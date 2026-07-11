# Architecture

LogicLeap is a modular monolith with HTTP and MCP adapters over the same typed
application services. PostgreSQL is authoritative. Application mutations and
append-only domain events commit in the same transaction.

Dependencies point inward: adapters depend on application services, application
services depend on domain policies, and infrastructure implements persistence.
Neither MCP nor HTTP accepts SQL or a generic entity-update command.

The containerized MCP adapter uses stateless Streamable HTTP at `/mcp`. Transport
wiring lives in `logicleap.mcp.server`, allowing a later STDIO entry point without
changing tools or application services.

