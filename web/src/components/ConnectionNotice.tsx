import { isNetworkError } from "../api";
import { Icon } from "./Icon";

/** True while a query is retrying after a connection error or paused because the browser is
 * offline. React Query keeps retrying with backoff and resumes on reconnect by itself. */
export function isReconnecting(query: { failureReason: unknown; fetchStatus: string }): boolean {
  return query.fetchStatus === "paused" || isNetworkError(query.failureReason);
}

export function ConnectionNotice() {
  return (
    <p className="connection-notice" role="status">
      <Icon name="spinner" size={14} />
      Connection lost, reconnecting…
    </p>
  );
}
