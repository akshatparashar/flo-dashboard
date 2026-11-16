import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Assistant } from "./Assistant";
import { RichText } from "./rich";

function reply(answer: string, extra: Record<string, unknown> = {}) {
  return { answer, page: "/fabric-po", page_label: "Fabric PO", context: { metric: "Total POs" }, understood: true, intent: "value", engine: "rules", ...extra };
}

function mockFetch(...bodies: Array<object | Error>) {
  const fn = vi.fn();
  for (const b of bodies) {
    if (b instanceof Error) fn.mockRejectedValueOnce(b);
    else fn.mockResolvedValueOnce({ ok: true, status: 200, json: async () => b });
  }
  vi.stubGlobal("fetch", fn);
  return fn;
}

function mount(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Assistant />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  sessionStorage.clear();
  localStorage.clear();
});
afterEach(() => vi.unstubAllGlobals());

describe("FLO Assistant", () => {
  it("opens from the robot, asks the API and shows the answer with a link to its page", async () => {
    const fetch = mockFetch(reply("Total POs is **170 POs**."), reply("Total POs in May-26 is **19 POs**."));
    mount("/");
    fireEvent.click(screen.getByRole("button", { name: "Open FLO Assistant" }));
    const box = screen.getByRole("textbox", { name: "Your question" });
    fireEvent.change(box, { target: { value: "total po count" } });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(await screen.findByText("170 POs")).toHaveProperty("tagName", "STRONG");
    expect(screen.getByRole("link", { name: /Open Fabric PO/ })).toHaveAttribute("href", "/fabric-po");
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("/api/chat");
    expect(JSON.parse(init.body)).toEqual({ message: "total po count", context: null });

    fireEvent.change(box, { target: { value: "and for may" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("19 POs");
    expect(JSON.parse(fetch.mock.calls[1][1].body).context).toEqual({ metric: "Total POs" });   // follow-up context
  });

  it("shows an error with a retry that asks again", async () => {
    mockFetch(new TypeError("offline"), reply("Pending is **8,470 pcs**."));
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Open FLO Assistant" }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "pending pcs" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/Can't reach the server/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByText("8,470 pcs");
    expect(screen.queryByText(/Can't reach the server/)).not.toBeInTheDocument();
    expect(screen.getAllByText("pending pcs")).toHaveLength(1);
  });

  it("closes with × or Escape, and tucks to the screen edge and back", async () => {
    mount();
    fireEvent.click(screen.getByRole("button", { name: "Open FLO Assistant" }));
    fireEvent.click(screen.getByRole("button", { name: "Close FLO Assistant" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open FLO Assistant" }));
    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Hide FLO Assistant/ }));
    expect(screen.queryByRole("button", { name: "Open FLO Assistant" })).not.toBeInTheDocument();
    expect(localStorage.getItem("flo-assistant-dock")).toBe("tucked");
    fireEvent.click(screen.getByRole("button", { name: "Show FLO Assistant" }));
    expect(screen.getByRole("button", { name: "Open FLO Assistant" })).toBeInTheDocument();
  });

  it("keeps the conversation when the page changes", async () => {
    mockFetch(reply("Total revenue is **₹33.99 Cr**."));
    const first = mount();
    fireEvent.click(screen.getByRole("button", { name: "Open FLO Assistant" }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "total revenue" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("₹33.99 Cr");
    first.unmount();
    mount("/target");
    fireEvent.click(screen.getByRole("button", { name: "Open FLO Assistant" }));
    expect(screen.getByText("₹33.99 Cr")).toBeInTheDocument();
  });
});

describe("RichText", () => {
  it("renders bold, bullets and numbered lines without injecting HTML", () => {
    const { container } = render(<RichText text={"Top 2:\n1. **A**: 5\n2. **B**: 3\n• note <img src=x onerror=alert(1)>"} />);
    expect(container.querySelectorAll("ol li")).toHaveLength(2);
    expect(container.querySelectorAll("ul li")).toHaveLength(1);
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});
