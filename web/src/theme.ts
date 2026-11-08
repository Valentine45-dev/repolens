// Light and dark. Light is the design reference. Until the user picks one, the theme follows the
// operating system (prefers-color-scheme) and changes with it; a pick is remembered in this browser.
// The script at the top of index.html applies the same rule before the first paint, so the page
// never flashes the wrong theme; keep the two in step (theme.dom.test.ts runs both).
import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

export const THEME_KEY = "repolens.theme";
export const TRANSITION_MS = 200;
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

let switchTimer: number | undefined;

/** The user's pick: remembered, applied, and eased over 200ms by a class that transitions only
 * colours (so graph pan, zoom and hover are never slowed). Under reduced motion it is instant. */
export function chooseTheme(theme: Theme): void {
  writeStored(theme);
  const root = document.documentElement;
  if (!matches(REDUCED_QUERY)) {
    root.classList.add("theme-switching");
    window.clearTimeout(switchTimer);
    switchTimer = window.setTimeout(() => root.classList.remove("theme-switching"), TRANSITION_MS);
  }
  applyTheme(theme);
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
