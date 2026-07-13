import inspect
from typing import Any

from logicleap.mcp import server


def test_epic_context_tools_are_registered_and_delegate_to_services() -> None:
    names = {
        "get_epic_context",
        "list_epic_context_history",
        "propose_epic_context",
        "propose_epic_context_improvement",
        "propose_epic_context_from_task",
        "approve_epic_context",
        "reject_epic_context",
        "deprecate_epic_context",
    }
    registered = set(server.mcp._tool_manager._tools)  # noqa: SLF001
    assert names <= registered
    for name in names:
        assert "services." in inspect.getsource(getattr(server, name))


def test_agent_working_context_omits_proposal_content() -> None:
    context: dict[str, Any] = {
        "epic_context": {
            "active": [{"id": "approved", "content": "Full approved content"}],
            "pending_proposals": [
                {
                    "id": "proposal",
                    "kind": "LESSON_LEARNED",
                    "title": "Possible learning",
                    "content": "Unapproved details",
                    "authority": "PROPOSED",
                    "status": "ACTIVE",
                    "supersedes_context_id": None,
                    "source_task_id": "task",
                }
            ],
        }
    }

    compact = server._compact_agent_working_context(context)

    assert compact["epic_context"]["active"][0]["content"] == "Full approved content"
    assert "content" not in compact["epic_context"]["pending_proposals"][0]
