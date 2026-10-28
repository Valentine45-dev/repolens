import type { Severity } from "../api";
import { Icon } from "./Icon";

const LABEL: Record<Severity, string> = { high: "High", medium: "Medium", low: "Low" };

/** Icon + word + colour, so severity never depends on colour alone. */
export function SeverityBadge({ severity }: { severity: Severity }) {
  return (
    <span className="severity" data-severity={severity}>
      <Icon name={`sev-${severity}`} size={14} />
      {LABEL[severity]}
    </span>
  );
}
