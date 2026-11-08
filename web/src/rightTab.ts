import { useEffect, useRef, useState } from "react";

export type RightTab = "panel" | "ask";

/** Which of Ask and the file or finding panel is in front when they share one column. A newly
 * picked file or finding comes to the front; opening Ask, or "Ask about this" (a new prefill),
 * brings Ask to the front. A link that opens both at once shows the panel first: the first render
 * changes nothing on the Ask side. */
export function useRightTab(panelParam: string | null, askOpen: boolean, askPrefill: string | null) {
  const [tab, setTab] = useState<RightTab>(panelParam !== null || !askOpen ? "panel" : "ask");
  useEffect(() => {
    if (panelParam !== null) setTab("panel");
  }, [panelParam]);
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
