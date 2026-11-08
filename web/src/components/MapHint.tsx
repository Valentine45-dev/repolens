import { useState } from "react";

import { CloseButton } from "./CloseButton";

export const MAP_HINT_KEY = "repolens.mapHintSeen";

function seen(): boolean {
  try {
    return window.localStorage.getItem(MAP_HINT_KEY) === "1";
  } catch {
    return false;
  }
}

/** First visit to the map: three lines on how to read it, at the bottom left of the canvas (the
 * React Flow credit is bottom right). Closed once, it stays closed in this browser. */
export function MapHint() {
  const [open, setOpen] = useState(() => !seen());
  if (!open) return null;
  const close = () => {
    setOpen(false);
    try {
      window.localStorage.setItem(MAP_HINT_KEY, "1");
    } catch {
      // Not remembered in this browser; it stays closed until the page is reloaded.
    }
  };
  return (
    <section className="map-hint" aria-labelledby="map-hint-title">
      <header className="map-hint-head">
        <h2 id="map-hint-title" className="map-hint-title">
          How to read this map
        </h2>
        <CloseButton what="map help" onClose={close} />
      </header>
      <ul>
        <li>A box is a folder or a file. Click a folder to open it, a file to read its code.</li>
        <li>A line means one imports or calls the other; its number says how many times.</li>
        <li>Hover or select a box to see all of its lines. Fit shows the whole map.</li>
      </ul>
      <button type="button" className="button button-secondary button-small" onClick={close}>
        Got it
      </button>
    </section>
  );
}
