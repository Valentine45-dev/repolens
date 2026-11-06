// Hover with a short delay, so sweeping the mouse across a map does not redraw it for every node
// it crosses. Entering a node shows its edges after `enterMs`; leaving clears them after
// `leaveMs`; moving from one node straight to the next never passes through "nothing".

export interface HoverIntent {
  enter(id: string): void;
  leave(): void;
  cancel(): void;
}

export function createHoverIntent(
  onChange: (id: string | null) => void,
  enterMs = 100,
  leaveMs = 60,
): HoverIntent {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let current: string | null = null;
  const schedule = (id: string | null, ms: number) => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      if (current !== id) {
        current = id;
        onChange(id);
      }
    }, ms);
  };
  return {
    enter: (id) => schedule(id, enterMs),
    leave: () => schedule(null, leaveMs),
    cancel: () => clearTimeout(timer),
  };
}
