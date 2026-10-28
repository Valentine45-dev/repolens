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

/** Put the middle of `el` in the middle of `container` (the browser clamps at the ends). */
export function scrollToCenter(container: HTMLElement, el: HTMLElement) {
  const slack = container.clientHeight - el.getBoundingClientRect().height;
  container.scrollTo({ top: offsetIn(container, el) - slack / 2 });
}
