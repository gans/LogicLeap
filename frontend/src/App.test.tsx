import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
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

let contextReads = 0;

const workingContext = () => ({
  task: { ...task, version: contextReads || 1 }, actors: [], requirements: [],
  acceptance_criteria: [], context_entries: [], questions: [], blockers: [], decisions: [],
  implementation_runs: [], evidence: [], reviews: [], timeline: [],
  allowed_transitions: [{ target_state: "READY_FOR_ANALYSIS", ready: true, missing: [], suggested: false }],
  epic_version: 1, task_version: contextReads || 1,
  epic_context: { active: [], pending_proposals: [] }, context_conflicts: [],
});

const activeContext = {
  id: "context-1", epic_id: epic.id, kind: "ARCHITECTURE", title: "Migration architecture",
  content: "Use an incremental strangler migration.", authority: "APPROVED", status: "ACTIVE",
  created_by_actor_id: actor.id, approved_by_actor_id: actor.id,
  approved_at: "2026-01-02T00:00:00Z", supersedes_context_id: null, source_task_id: null,
  source_context_id: null, source_decision_id: null, source_evidence_id: null, source_uri: null,
  is_required_for_analysis: false, is_required_for_implementation: true,
  rejection_reason: null, deprecation_reason: null, version: 1,
  created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-02T00:00:00Z",
};
const pendingContext = {
  ...activeContext, id: "proposal-1", title: "Updated architecture",
  content: "Use staged strangler releases.", authority: "PROPOSED",
  approved_by_actor_id: null, approved_at: null, supersedes_context_id: activeContext.id,
};

const jsonResponse = (body: unknown) =>
  Promise.resolve({ ok: true, json: () => Promise.resolve(body) } as Response);

function LocationProbe() {
  const location = useLocation();
  return <output data-testid="location">{location.pathname}</output>;
}

function BrowserBack() {
  const navigate = useNavigate();
  return <button onClick={() => navigate(-1)}>Browser back</button>;
}

function renderAt(path: string, entries = [path], initialIndex = entries.length - 1) {
  return render(
    <MemoryRouter initialEntries={entries} initialIndex={initialIndex}>
      <LocationProbe />
      <BrowserBack />
      <App />
    </MemoryRouter>,
  );
}

describe("route-driven navigation", () => {
  beforeEach(() => {
    contextReads = 0;
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "POST") return jsonResponse({ ...task, version: 2 });
      if (url.endsWith("/actors")) return jsonResponse([actor]);
      if (url.endsWith("/epics")) return jsonResponse([epic]);
      if (url.endsWith(`/epics/${epic.id}`)) return jsonResponse(epic);
      if (url.endsWith(`/epics/${epic.id}/tasks`)) return jsonResponse([task]);
      if (url.includes(`/epics/${epic.id}/contexts?`)) return jsonResponse([activeContext, pendingContext]);
      if (url.endsWith(`/epics/${epic.id}/context-history`)) return jsonResponse([activeContext, pendingContext]);
      if (url.endsWith(`/epics/${epic.id}/timeline`)) return jsonResponse([]);
      if (url.endsWith(`/tasks/${task.id}/working-context`)) {
        contextReads += 1;
        return jsonResponse(workingContext());
      }
      return jsonResponse([]);
    }));
  });

  it("renders the epic list at the root route", async () => {
    renderAt("/");
    expect(await screen.findByRole("heading", { name: "All epics" })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /Migration epic/ }).length).toBeGreaterThan(0);
  });

  it("navigates to the epic URL when an epic is selected", async () => {
    renderAt("/");
    fireEvent.click((await screen.findAllByRole("link", { name: /Migration epic/ }))[0]);
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent(`/epics/${epic.id}`));
    expect(await screen.findByRole("heading", { name: epic.title })).toBeInTheDocument();
  });

  it("navigates to the task URL when a task is selected", async () => {
    renderAt(`/epics/${epic.id}`);
    fireEvent.click(await screen.findByRole("button", { name: /Migrate accounts/ }));
    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent(`/epics/${epic.id}/tasks/${task.id}`));
    expect(await screen.findByText(taskId)).toBeInTheDocument();
  });

  it("loads and renders an epic from a direct epic URL", async () => {
    renderAt(`/epics/${epic.id}`);
    expect(await screen.findByRole("heading", { name: epic.title })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Migrate accounts/ })).toBeInTheDocument();
  });

  it("loads complete task context from a direct task URL", async () => {
    renderAt(`/epics/${epic.id}/tasks/${task.id}`);
    expect(await screen.findByRole("heading", { name: task.title })).toBeInTheDocument();
    expect(screen.getByText(task.objective)).toBeInTheDocument();
    expect(contextReads).toBe(1);
  });

  it("preserves the task page when mounted again at the same URL", async () => {
    const first = renderAt(`/epics/${epic.id}/tasks/${task.id}`);
    expect(await screen.findByRole("heading", { name: task.title })).toBeInTheDocument();
    first.unmount();

    renderAt(`/epics/${epic.id}/tasks/${task.id}`);
    expect(await screen.findByRole("heading", { name: task.title })).toBeInTheDocument();
    expect(screen.getByTestId("location")).toHaveTextContent(`/epics/${epic.id}/tasks/${task.id}`);
  });

  it("returns from task to epic through browser history", async () => {
    renderAt(
      `/epics/${epic.id}/tasks/${task.id}`,
      [`/epics/${epic.id}`, `/epics/${epic.id}/tasks/${task.id}`],
      1,
    );
    expect(await screen.findByRole("heading", { name: task.title })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Browser back" }));

    await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent(`/epics/${epic.id}`));
    expect(await screen.findByRole("heading", { name: epic.title })).toBeInTheDocument();
  });

  it("shows a useful error for an invalid task ID", async () => {
    renderAt(`/epics/${epic.id}/tasks/missing-task`);
    expect(await screen.findByText("Task not found in this epic.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to epic list" })).toHaveAttribute("href", "/");
  });

  it("refreshes task context after a mutation without changing the URL", async () => {
    renderAt(`/epics/${epic.id}/tasks/${task.id}`);
    fireEvent.click(await screen.findByRole("button", { name: "Transition" }));

    await waitFor(() => expect(contextReads).toBe(2));
    expect(screen.getByTestId("location")).toHaveTextContent(`/epics/${epic.id}/tasks/${task.id}`);
    expect(await screen.findByRole("heading", { name: task.title })).toBeInTheDocument();
  });

  it("copies only the raw task UUID and shows feedback", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    renderAt(`/epics/${epic.id}/tasks/${task.id}`);

    fireEvent.click(await screen.findByRole("button", { name: "Copy task ID" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(taskId));
    expect(writeText).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("displays active epic context and history", async () => {
    renderAt(`/epics/${epic.id}`);
    expect(await screen.findByRole("heading", { name: "Active context" })).toBeInTheDocument();
    expect(screen.getAllByText(activeContext.title).length).toBeGreaterThan(0);
    expect(screen.getByText("History (2)")).toBeInTheDocument();
  });

  it("adds epic context and stays on the epic route", async () => {
    renderAt(`/epics/${epic.id}`);
    fireEvent.click(await screen.findByText("＋ Add epic context"));
    fireEvent.change(screen.getByPlaceholderText("Context title"), { target: { value: "Business rules" } });
    fireEvent.change(screen.getByPlaceholderText("Shared knowledge"), { target: { value: "Preserve account identifiers." } });
    fireEvent.click(screen.getAllByRole("button", { name: "Submit proposal" }).at(-1)!);
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(expect.stringContaining(`/epics/${epic.id}/contexts`), expect.objectContaining({ method: "POST" })));
    expect(screen.getByTestId("location")).toHaveTextContent(`/epics/${epic.id}`);
  });

  it("proposes a replacement", async () => {
    renderAt(`/epics/${epic.id}`);
    fireEvent.click(await screen.findByText("Propose improvement"));
    fireEvent.change(screen.getByDisplayValue(activeContext.content), { target: { value: "Use staged releases." } });
    fireEvent.click(screen.getAllByRole("button", { name: "Submit proposal" })[0]);
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(expect.stringContaining(`/contexts/${activeContext.id}/propose-replacement`), expect.objectContaining({ method: "POST" })));
  });

  it("lets the architect approve and reject proposals", async () => {
    renderAt(`/epics/${epic.id}`);
    fireEvent.click(await screen.findByRole("button", { name: "Approve" }));
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(expect.stringContaining(`/contexts/${pendingContext.id}/approve`), expect.objectContaining({ method: "POST" })));
    fireEvent.change(screen.getByPlaceholderText("Rejection reason"), { target: { value: "Needs evidence" } });
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(expect.stringContaining(`/contexts/${pendingContext.id}/reject`), expect.objectContaining({ method: "POST" })));
  });

  it("promotes task learning without leaving the task route", async () => {
    renderAt(`/epics/${epic.id}/tasks/${task.id}`);
    fireEvent.click(await screen.findByText("Promote to epic context"));
    fireEvent.change(screen.getByPlaceholderText("Learning title"), { target: { value: "Ordering risk" } });
    fireEvent.change(screen.getByPlaceholderText("Proposed learning"), { target: { value: "Legacy events can arrive out of order." } });
    fireEvent.click(screen.getByRole("button", { name: "Submit proposal" }));
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalledWith(expect.stringContaining("promote-task-learning"), expect.objectContaining({ method: "POST" })));
    expect(screen.getByTestId("location")).toHaveTextContent(`/epics/${epic.id}/tasks/${task.id}`);
  });
});
