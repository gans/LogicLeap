from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "LogicLeap",
    instructions="Typed tools for human-controlled SDLC coordination.",
    stateless_http=True,
    json_response=True,
    host="0.0.0.0",
    port=8001,
)


@mcp.tool()
def health() -> dict[str, str]:
    """Report that the LogicLeap MCP process is running."""
    return {"status": "ok"}


def run_streamable_http() -> None:
    """Run the container transport; other transports remain separate wiring concerns."""
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    run_streamable_http()
