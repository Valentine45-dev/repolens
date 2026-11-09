// Light and dark. Light is the design reference. Until the user picks one, the theme follows the
// operating system (prefers-color-scheme) and changes with it; a pick is remembered in this browser.
// The script at the top of index.html applies the same rule before the first paint, so the page
// never flashes the wrong theme; keep the two in step (theme.dom.test.ts runs both).
import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

export const THEME_KEY = "repolens.theme";
/** How long the circular reveal of a new theme takes. */
export const REVEAL_MS = 450;
/** On <html> only while the variables are swapped: turns every transition off (styles.css). */
export const INSTANT_CLASS = "theme-instant";
/** On <html> only while a reveal runs: the View Transition shows just the circle (styles.css). */
export const REVEAL_CLASS = "theme-reveal";
/** Set on <html> only while a reveal runs: the circle's centre, final radius and duration. */
export const REVEAL_VARS = {
  x: "--theme-reveal-x",
  y: "--theme-reveal-y",
  radius: "--theme-reveal-r",
  duration: "--theme-reveal-ms",
} as const;
const DARK_QUERY = "(prefers-color-scheme: dark)";
const REDUCED_QUERY = "(prefers-reduced-motion: reduce)";

/** A stored pick wins; anything else (nothing stored, a value we do not know) follows the OS. */
export function resolveTheme(stored: string | null, systemDark: boolean): Theme {
  if (stored === "light" || stored === "dark") return stored;
  return systemDark ? "dark" : "light";
}

/** localStorage can be missing or throw (private windows, blocked site data): never fatal. */
export function readStored(): string | null {
  try {
    return window.localStorage.getItem(THEME_KEY);
  } catch {
    return null;
  }
}

function writeStored(theme: Theme): void {
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    // Not remembered in this browser; the choice still holds for this page.
  }
}

function matches(query: string): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia(query).matches;
}

export function currentTheme(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

export function applyTheme(theme: Theme): void {
  const root = document.documentElement;
  root.dataset.theme = theme;
  root.style.colorScheme = theme;
  listeners.forEach((l) => l());
}

/** Swap the theme with every CSS transition off for that one style change, so nothing eases on its
 * own (buttons and map nodes have hover colour transitions) and the first frame is all one theme.
 * Reading one style makes the browser compute the new colours while the class is still on. */
export function applyThemeInstantly(theme: Theme): void {
  const root = document.documentElement;
  root.classList.add(INSTANT_CLASS);
  try {
    applyTheme(theme);
    void window.getComputedStyle(document.body ?? root).color;
  } finally {
    root.classList.remove(INSTANT_CLASS);
  }
}

// The parts of the View Transitions API used here (not every browser has it).
interface ViewTransitionLike {
  ready: Promise<unknown>;
  finished: Promise<unknown>;
}
type StartViewTransition = (update: () => void) => ViewTransitionLike;

let revealing = false;

/** The user's pick from the toggle: remembered and applied. Where the browser has View Transitions
 * and motion is allowed, the new theme is revealed by a circle that grows from the toggle's centre
 * (its box, not the pointer, so a keyboard press looks the same) to the farthest window corner; the
 * page underneath switches instantly, so no element is transitioned and pan, zoom and hover are
 * never slowed. Otherwise (no support, reduced motion, no origin) the switch is instant. A pick
 * made while a reveal is still running is ignored, so reveals never stack. */
export function chooseTheme(theme: Theme, origin?: Element | null): void {
  if (revealing) return;
  writeStored(theme);
  const start = (document as unknown as { startViewTransition?: StartViewTransition }).startViewTransition;
  if (!origin || typeof start !== "function" || matches(REDUCED_QUERY)) {
    applyThemeInstantly(theme);
    return;
  }

  const root = document.documentElement;
  const box = origin.getBoundingClientRect();
  const x = box.left + box.width / 2;
  const y = box.top + box.height / 2;
  const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));

  // The circle is a CSS animation on ::view-transition-new(root) (styles.css) that reads these
  // properties. (Firefox 159 does not apply element.animate() to View Transition pseudo-elements;
  // CSS animations on them work in every browser that has View Transitions.)
  const reveal: Record<string, string> = {
    [REVEAL_VARS.x]: `${x}px`,
    [REVEAL_VARS.y]: `${y}px`,
    [REVEAL_VARS.radius]: `${radius}px`,
    [REVEAL_VARS.duration]: `${REVEAL_MS}ms`,
  };
  revealing = true;
  for (const [name, value] of Object.entries(reveal)) root.style.setProperty(name, value);
  root.classList.add(REVEAL_CLASS);
  const done = () => {
    revealing = false;
    root.classList.remove(REVEAL_CLASS);
    for (const name of Object.keys(reveal)) root.style.removeProperty(name);
  };
  let transition: ViewTransitionLike;
  try {
    transition = start.call(document, () => applyThemeInstantly(theme));
  } catch {
    done();
    applyThemeInstantly(theme);
    return;
  }
  // Skipped (for example the tab was hidden): the update callback still applies the theme.
  transition.ready.catch(() => {});
  // Finished, skipped or failed: never leave the class, the properties or the guard behind.
  transition.finished.then(done, done);
}

const listeners = new Set<() => void>();

/** Follow the OS while nothing is stored. Call once at start; returns a function that stops it. */
export function followSystem(): () => void {
  if (typeof window.matchMedia !== "function") return () => {};
  const list = window.matchMedia(DARK_QUERY);
  // Only while no pick is stored does the OS decide.
  const onChange = () => applyTheme(resolveTheme(readStored(), list.matches));
  list.addEventListener("change", onChange);
  return () => list.removeEventListener("change", onChange);
}

export function useTheme(): Theme {
  return useSyncExternalStore(
    (onChange) => {
      listeners.add(onChange);
      return () => listeners.delete(onChange);
    },
    currentTheme,
    () => "light",
  );
}

/** For main.tsx: make sure the page has a theme even if the inline script did not run. */
export function initTheme(): void {
  if (!document.documentElement.dataset.theme) applyTheme(resolveTheme(readStored(), matches(DARK_QUERY)));
  followSystem();
}
