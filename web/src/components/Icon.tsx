// A handful of authored line icons (one stroke weight, 16px grid) instead of an icon library.

import type { ReactNode } from "react";

type IconName =
  | "check"
  | "x"
  | "circle"
  | "spinner"
  | "arrow-right"
  | "sev-high"
  | "sev-medium"
  | "sev-low"
  | "send"
  | "copy";

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
  // Severity: shape as well as colour (spec 5.6: never colour alone).
  "sev-high": <path d="M8 2.5 14 13H2L8 2.5Zm0 4v3m0 1.75v.25" />,
  "sev-medium": (
    <>
      <circle cx="8" cy="8" r="5.5" />
      <path d="M8 5v3.25m0 2v.25" />
    </>
  ),
  "sev-low": <circle cx="8" cy="8" r="3" />,
  send: <path d="M2.5 8h9m-3.5-4 4 4-4 4" />,
  copy: (
    <>
      <rect x="5.5" y="5.5" width="8" height="8" rx="1.5" />
      <path d="M10.5 3.5V3A1.5 1.5 0 0 0 9 1.5H3A1.5 1.5 0 0 0 1.5 3v6A1.5 1.5 0 0 0 3 10.5h.5" />
    </>
  ),
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
