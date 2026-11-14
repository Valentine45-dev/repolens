// "Go to file" opens with Ctrl+K (Cmd+K on a Mac) or "/", but never while the user is typing.

const TEXT_INPUTS = new Set(["text", "search", "url", "email", "tel", "password", "number", "date",
  "datetime-local", "month", "time", "week"]);

/** Focus is somewhere keys type text: a text field, a textarea, a select or editable content. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  if (target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return true;
  if (target instanceof HTMLInputElement) return TEXT_INPUTS.has(target.type || "text");
  return false;
}

export function isGoToFileShortcut(e: KeyboardEvent): boolean {
  if (e.defaultPrevented || e.isComposing || e.repeat) return false;
  if (isTypingTarget(e.target)) return false;
  const key = e.key.toLowerCase();
  if (key === "k") return (e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey;
  return e.key === "/" && !e.ctrlKey && !e.metaKey && !e.altKey;
}

/** Shown on the button: the shortcut as this computer writes it. */
export function shortcutLabel(platform = typeof navigator === "undefined" ? "" : navigator.platform): string {
  return /mac|iphone|ipad/i.test(platform) ? "⌘ K" : "Ctrl K";
}
