import { useEffect, useRef, useState } from "react";

export type RightTab = "panel" | "ask";

/** Which of Ask and the file or finding panel is in front when they share one column. Anything
 * that opens a file, a finding or lines comes to the front: a new panel, new lines, or a link
 * that carries REVEAL (`reveal`, links.ts), so a citation chip shows its code even when that file
 * is already open behind Ask. Opening Ask, or "Ask about this" (a new prefill), brings Ask to the
 * front. A link that opens both at once shows the panel first: the first render changes nothing
 * on the Ask side. */
export function useRightTab(
  panelParam: string | null,
  askOpen: boolean,
  askPrefill: string | null,
  lines: string | null = null,
  reveal: string | null = null,
) {
  const [tab, setTab] = useState<RightTab>(panelParam !== null || !askOpen ? "panel" : "ask");
  useEffect(() => {
    if (panelParam !== null) setTab("panel");
  }, [panelParam, lines, reveal]);
  const seen = useRef({ askOpen, askPrefill });
  useEffect(() => {
    const before = seen.current;
    seen.current = { askOpen, askPrefill };
    if ((askOpen && !before.askOpen) || (askPrefill !== null && askPrefill !== before.askPrefill)) {
      setTab("ask");
    }
  }, [askOpen, askPrefill]);
  return [tab, setTab] as const;
}
