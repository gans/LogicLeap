import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { App } from "./App";

globalThis.fetch = vi.fn(() =>
  Promise.resolve({ ok: true, json: () => Promise.resolve([]) } as Response),
);

describe("App", () => {
  it("renders the product name", async () => {
    render(<App />);
    expect(await screen.findByRole("heading", { name: "LogicLeap" })).toBeInTheDocument();
  });
});
