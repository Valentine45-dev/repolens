import { describe, expect, it } from "vitest";

import type { MapEdge } from "./api";
import { createFocusStore, EDGE_ACTIVE, EDGE_VISIBLE, NODE_NEAR, NODE_SELECTED } from "./focusStore";

const e = (source: string, target: string): MapEdge => ({
  source, target, count: 1, confidence: 1, guess: false,
});
const edges = [e("a", "b"), e("c", "a"), e("d", "x")];

describe("focus store", () => {
  it("is quiet with no focus: nothing near, resting edges visible", () => {
    const s = createFocusStore();
    s.configure(edges, null);
    expect(s.focusing()).toBe(false);
    expect(s.nodeFlags("a")).toBe(0);
    expect(s.edgeFlags("a", "b", true)).toBe(EDGE_VISIBLE);
    expect(s.edgeFlags("a", "b", false)).toBe(0);
  });

  it("hover marks the node and its neighbours, shows and activates its edges", () => {
    const s = createFocusStore();
    s.configure(edges, null);
    s.setHover("a");
    expect(s.focusing()).toBe(true);
    expect(s.nodeFlags("a")).toBe(NODE_NEAR);
    expect(s.nodeFlags("b")).toBe(NODE_NEAR);
    expect(s.nodeFlags("c")).toBe(NODE_NEAR);
    expect(s.nodeFlags("d")).toBe(0);
    expect(s.edgeFlags("a", "b", false)).toBe(EDGE_ACTIVE | EDGE_VISIBLE);
    expect(s.edgeFlags("d", "x", false)).toBe(0); // a hidden edge elsewhere stays hidden
    expect(s.edgeFlags("d", "x", true)).toBe(EDGE_VISIBLE); // a resting one stays, unactive
    s.setHover(null);
    expect(s.focusing()).toBe(false);
    expect(s.edgeFlags("a", "b", false)).toBe(0);
  });

  it("hover beats keyboard focus beats selection, and selection comes back", () => {
    const s = createFocusStore();
    s.configure(edges, "d");
    expect(s.nodeFlags("d")).toBe(NODE_SELECTED | NODE_NEAR);
    s.setFocused("c");
    expect(s.nodeFlags("c")).toBe(NODE_NEAR);
    s.setHover("b");
    expect(s.nodeFlags("b")).toBe(NODE_NEAR);
    expect(s.nodeFlags("c")).toBe(0);
    s.setHover(null);
    s.setFocused(null);
    expect(s.nodeFlags("d")).toBe(NODE_SELECTED | NODE_NEAR);
  });

  it("tells subscribers only when the focus really changes", () => {
    const s = createFocusStore();
    s.configure(edges, null);
    let calls = 0;
    const off = s.subscribe(() => calls++);
    s.setHover("a");
    s.setHover("a");
    expect(calls).toBe(1);
    s.setHover(null);
    expect(calls).toBe(2);
    off();
    s.setHover("b");
    expect(calls).toBe(2);
  });

  it("a new view resets what is near", () => {
    const s = createFocusStore();
    s.configure(edges, "a");
    expect(s.nodeFlags("b")).toBe(NODE_NEAR);
    s.configure([e("a", "z")], "a");
    expect(s.nodeFlags("b")).toBe(0);
    expect(s.nodeFlags("z")).toBe(NODE_NEAR);
  });
});
