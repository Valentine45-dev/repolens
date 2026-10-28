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
  | "copy"
  | "file"
  | "package"
  | "symbol"
  | "graph"
  | "spark"
  | "expand"
  | "collapse";

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
  // Ask drawer: what a result is (file, package, function/class), what answered, drawer size.
  file: <path d="M4 1.75h5L12.25 5v9.25H4zM9 1.75V5h3.25" />,
  package: <path d="M8 1.75 13.5 4.5v7L8 14.25 2.5 11.5v-7zM2.5 4.5 8 7.25l5.5-2.75M8 7.25v7" />,
  symbol: (
    <path d="M6 2.5c-1.25 0-1.75.75-1.75 2v1.5c0 1-.5 1.75-1.5 2 1 .25 1.5 1 1.5 2v1.5c0 1.25.5 2 1.75 2m4-11c1.25 0 1.75.75 1.75 2v1.5c0 1 .5 1.75 1.5 2-1 .25-1.5 1-1.5 2v1.5c0 1.25-.5 2-1.75 2" />
  ),
  graph: (
    <>
      <circle cx="4" cy="4" r="1.75" />
      <circle cx="12" cy="4" r="1.75" />
      <circle cx="8" cy="12" r="1.75" />
      <path d="M5.75 4h4.5M4.9 5.5l2.2 4.9m3.9-4.9-2.2 4.9" />
    </>
  ),
  spark: <path d="M8 1.75 9.4 6.6 14.25 8 9.4 9.4 8 14.25 6.6 9.4 1.75 8 6.6 6.6z" />,
  expand: <path d="M9.5 2.5h4v4M6.5 13.5h-4v-4M13.5 2.5 9 7M2.5 13.5 7 9" />,
  collapse: <path d="M13.5 6.5h-4v-4M2.5 9.5h4v4M9.5 6.5l4-4M6.5 9.5l-4 4" />,
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
