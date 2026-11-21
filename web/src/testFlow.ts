// Test helper: what React Flow needs from the DOM that jsdom does not give (sizes, ResizeObserver,
// DOMMatrixReadOnly). A node (and anything in it) is 200x44, everything else 1000x800, so nodes and edges
// render as in a browser. Returns a function that puts everything back.
const SIZES = ["offsetWidth", "offsetHeight", "clientWidth", "clientHeight"] as const;

export function mockReactFlowDom(): () => void {
  const g = globalThis as Record<string, unknown>;
  const proto = HTMLElement.prototype as unknown as Record<string, unknown>;
  const saved = {
    ResizeObserver: g.ResizeObserver,
    DOMMatrixReadOnly: g.DOMMatrixReadOnly,
    sizes: SIZES.map((k) => [k, Object.getOwnPropertyDescriptor(proto, k)] as const),
  };
  // Reports a size once, as a browser does when an element is first observed: React Flow measures
  // nodes (and their handles) from this, and draws edges only once both ends are measured.
  g.ResizeObserver = class {
    constructor(private readonly callback: (entries: object[], observer: unknown) => void) {}
    observe(target: HTMLElement) {
      const contentRect = { width: target.offsetWidth, height: target.offsetHeight, top: 0, left: 0 };
      queueMicrotask(() => this.callback([{ target, contentRect }], this));
    }
    unobserve() {}
    disconnect() {}
  };
  g.DOMMatrixReadOnly = class {
    m22 = 1;
  };
  const big = (el: HTMLElement) => el.closest(".react-flow__node") === null;
  for (const k of SIZES) {
    const wide = k.endsWith("Width");
    Object.defineProperty(proto, k, {
      configurable: true,
      get(this: HTMLElement) {
        return big(this) ? (wide ? 1000 : 800) : wide ? 200 : 44;
      },
    });
  }
  return () => {
    g.ResizeObserver = saved.ResizeObserver;
    g.DOMMatrixReadOnly = saved.DOMMatrixReadOnly;
    for (const [k, d] of saved.sizes) {
      if (d) Object.defineProperty(proto, k, d);
      else delete proto[k];
    }
  };
}
