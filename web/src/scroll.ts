// Scroll one container only. Element.scrollIntoView scrolls every scrollable ancestor, the
// window included, which moved the whole page whenever it was even slightly scrollable.

/** Where `el` sits inside `container`'s scrollable content, from the content's top. */
function offsetIn(container: HTMLElement, el: HTMLElement): number {
  return el.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop;
}

/** Put the top of `el` at the top of `container`. */
export function scrollToStart(container: HTMLElement, el: HTMLElement) {
  container.scrollTo({ top: offsetIn(container, el) });
}

/** Bring a highlighted range into view: centred when it fits with `context` px to spare above and
 * below, otherwise its first line `context` px below the top (never flush with the edge). Instant
 * unless `smooth` (the caller passes false under reduced motion). */
export function scrollToRange(container: HTMLElement, el: HTMLElement, context: number, smooth = false) {
  const room = container.clientHeight;
  const height = el.getBoundingClientRect().height;
  const above = height + 2 * context <= room ? (room - height) / 2 : context;
  container.scrollTo({ top: Math.max(0, offsetIn(container, el) - above), behavior: smooth ? "smooth" : "auto" });
}
