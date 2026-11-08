import { Icon } from "./Icon";

/** The same close button on every side panel: an x, "Close (Esc)" on hover, and a name that says
 * which panel it closes. */
export function CloseButton({ what, onClose }: { what: string; onClose: () => void }) {
  return (
    <button type="button" className="icon-button" onClick={onClose} aria-label={`Close ${what} (Esc)`} title="Close (Esc)">
      <Icon name="x" />
    </button>
  );
}
