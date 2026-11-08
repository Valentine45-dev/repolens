import { useEffect, useRef, useState } from "react";

/** For loaders that appear in place over content that is already there (the map while the next
 * folder loads). Turns on only after `delay` ms, so a fast load shows nothing at all, and once on
 * stays on for at least `min` ms, so a slow-ish load does not blink. Layout-keeping skeletons (a
 * page or panel drawn before its data) do not use this: they show at once, or the page would be
 * blank for the delay. */
export function useDelayedFlag(on: boolean, delay = 200, min = 400): boolean {
  const [shown, setShown] = useState(false);
  const shownAt = useRef(0);
  useEffect(() => {
    if (on && !shown) {
      const t = setTimeout(() => {
        shownAt.current = Date.now();
        setShown(true);
      }, delay);
      return () => clearTimeout(t);
    }
    if (!on && shown) {
      const left = min - (Date.now() - shownAt.current);
      const t = setTimeout(() => setShown(false), Math.max(left, 0));
      return () => clearTimeout(t);
    }
    return undefined;
  }, [on, shown, delay, min]);
  return shown;
}
