// A handful of authored line icons (one stroke weight, 16px grid) instead of an icon library:
// the shell needs five glyphs.

import type { ReactNode } from "react";

type IconName = "check" | "x" | "circle" | "spinner" | "arrow-right";

const PATHS: Record<IconName, ReactNode> = {
  check: <path d="M3.5 8.5l3 3 6-7" />,
  x: <path d="M4.5 4.5l7 7m0-7l-7 7" />,
  circle: <circle cx="8" cy="8" r="4.5" />,
  spinner: (
    <>
      <circle cx="8" cy="8" r="5.5" opacity="0.25" />
      <path d="M8 2.5a5.5 5.5 0 0 1 5.5 5.5" />
    </>
  ),
  "arrow-right": <path d="M3 8h10m-4-4 4 4-4 4" />,
};

export function Icon({ name, size = 16, label }: { name: IconName; size?: number; label?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={name === "spinner" ? "spin" : undefined}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    >
      {PATHS[name]}
    </svg>
  );
}
