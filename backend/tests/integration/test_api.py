from uuid import uuid4

from fastapi.testclient import TestClient

from logicleap.main import app


def test_create_epic_and_task_inherits_architect() -> None:
    client = TestClient(app)
    actor = client.post(
        "/api/v1/actors",
        json={"display_name": f"Architect {uuid4()}", "kind": "HUMAN"},
    ).json()
    epic_response = client.post(
        "/api/v1/epics",
        json={
            "title": "Migrate legacy platform",
            "summary": "Migration coordination",
            "problem_statement": "The legacy platform is unsupported",
            "desired_outcome": "A supported production platform",
            "architect_actor_id": actor["id"],
            "acting_actor_id": actor["id"],
        },
    )
    assert epic_response.status_code == 201

    task_response = client.post(
        f"/api/v1/epics/{epic_response.json()['id']}/tasks",
        json={
            "title": "Inventory integrations",
            "summary": "Catalog dependencies",
            "objective": "Produce an integration inventory",
            "acting_actor_id": actor["id"],
        },
    )

    assert task_response.status_code == 201
    task = task_response.json()
    assert task["architect_actor_id"] == actor["id"]
    assert task["version"] == 1

    assignment = client.post(
        f"/api/v1/tasks/{task['id']}/actors",
        json={
            "actor_id": actor["id"],
            "role": "ARCHITECT",
            "acting_actor_id": actor["id"],
            "expected_version": 1,
        },
    )
    assert assignment.status_code == 201

    readiness = client.get(
        f"/api/v1/tasks/{task['id']}/readiness",
        params={"target": "READY_FOR_ANALYSIS"},
    )
    assert readiness.status_code == 200
    assert readiness.json()["ready"] is True

    working_context = client.get(f"/api/v1/tasks/{task['id']}/working-context")
    assert working_context.status_code == 200
    assert [event["type"] for event in working_context.json()["timeline"]] == [
        "TaskCreated",
        "ActorAddedToTask",
    ]
