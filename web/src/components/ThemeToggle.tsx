import { chooseTheme, useTheme } from "../theme";
import { Icon } from "./Icon";

/** Two states, light and dark. Until it is pressed the page follows the system setting. A toggle
 * button with a fixed name ("Dark theme") whose pressed state says which theme is on. */
export function ThemeToggle() {
  const dark = useTheme() === "dark";
  return (
    <button
      type="button"
      className="icon-button theme-toggle"
      aria-pressed={dark}
      aria-label="Dark theme"
      title="Dark theme (follows your system until you choose)"
      onClick={(event) => chooseTheme(dark ? "light" : "dark", event.currentTarget)}
    >
      <Icon name={dark ? "moon" : "sun"} />
    </button>
  );
}
