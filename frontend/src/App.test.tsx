import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";

const taskId = "8feecf24-d9f8-4e6b-9149-76f2ed72c852";
const actor = { id: "actor-1", display_name: "Ada", kind: "HUMAN" };
const epic = {
  id: "epic-1", title: "Migration epic", summary: "Summary",
  problem_statement: "Problem", desired_outcome: "Outcome",
  architect_actor_id: actor.id, version: 1, created_at: "2026-01-01T00:00:00Z",
};
const task = {
  id: taskId, epic_id: epic.id, title: "Migrate accounts", summary: "Task summary",
  objective: "Move account data", state: "DRAFT", blocked_from_state: null,
  architect_actor_id: actor.id, version: 1, created_at: "2026-01-01T00:00:00Z",
};
const workingContext = {
  task, actors: [], requirements: [], acceptance_criteria: [], context_entries: [],
  questions: [], blockers: [], decisions: [], implementation_runs: [], evidence: [],
  reviews: [], timeline: [], allowed_transitions: [],
};

const jsonResponse = (body: unknown) =>
  Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response);

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith("/actors")) return jsonResponse([actor]);
      if (url.endsWith("/epics")) return jsonResponse([epic]);
      if (url.endsWith(`/epics/${epic.id}/tasks`)) return jsonResponse([task]);
      if (url.endsWith(`/tasks/${task.id}/working-context`)) return jsonResponse(workingContext);
      return jsonResponse([]);
    }));
  });

  it("renders the product name", async () => {
    render(<App />);
    expect(await screen.findByRole("heading", { name: "LogicLeap" })).toBeInTheDocument();
  });

  it("copies only the raw task UUID and shows feedback", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });

    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Migration epic/ }));
    fireEvent.click(await screen.findByRole("button", { name: /Migrate accounts/ }));

    expect(await screen.findByText(taskId)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Copy task ID" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith(taskId));
    expect(writeText).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument();
  });
});
