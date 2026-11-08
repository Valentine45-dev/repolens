import { afterEach, describe, expect, it, vi } from "vitest";

import { delayHandler, devApiDelay } from "../devApiDelay";

afterEach(() => vi.useRealTimers());

describe("dev API delay (vite dev and preview server only)", () => {
  it("registers nothing when the variable is unset, empty, zero or not a number", () => {
    for (const env of [{}, { REPOLENS_DEV_API_DELAY_MS: "" }, { REPOLENS_DEV_API_DELAY_MS: "0" },
      { REPOLENS_DEV_API_DELAY_MS: "soon" }]) {
      expect(devApiDelay(env)).toBeNull();
      expect(delayHandler(env)).toBeNull();
    }
  });

  it("is a plugin for both the dev and the preview server when set", () => {
    const plugin = devApiDelay({ REPOLENS_DEV_API_DELAY_MS: "500" });
    expect(plugin?.configureServer).toBeTypeOf("function");
    expect(plugin?.configurePreviewServer).toBeTypeOf("function");
  });

  it("holds /api requests for the given time and lets everything else through", () => {
    vi.useFakeTimers();
    const handler = delayHandler({ REPOLENS_DEV_API_DELAY_MS: "500" })!;
    const api = vi.fn();
    const page = vi.fn();
    handler({ url: "/api/snapshots/2/status" }, {}, api);
    handler({ url: "/assets/index.js" }, {}, page);
    expect(page).toHaveBeenCalledOnce();
    expect(api).not.toHaveBeenCalled();
    vi.advanceTimersByTime(499);
    expect(api).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(api).toHaveBeenCalledOnce();
  });

  it("delays only matching paths when a pattern is given", () => {
    const handler = delayHandler({ REPOLENS_DEV_API_DELAY_MS: "500", REPOLENS_DEV_API_DELAY_MATCH: "/reach" })!;
    const other = vi.fn();
    handler({ url: "/api/snapshots/2/findings" }, {}, other);
    expect(other).toHaveBeenCalledOnce();
  });
});
