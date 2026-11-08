import type { Plugin } from "vite";

type Handler = (req: { url?: string }, res: unknown, next: () => void) => void;

/** Development aid, off unless REPOLENS_DEV_API_DELAY_MS is set: holds every /api request (or only
 * those whose path matches REPOLENS_DEV_API_DELAY_MATCH, a regular expression) for that many ms in
 * the dev or preview server, so loading states can be seen and checked. It lives in the Node
 * server, not in the app: no VITE_ prefix, so the value never reaches the browser bundle, and an
 * unset variable registers nothing at all. */
export function devApiDelay(env: Record<string, string | undefined>): Plugin | null {
  const handler = delayHandler(env);
  if (!handler) return null;
  const install = (server: { config: { logger: { warn: (m: string) => void } }; middlewares: unknown }) => {
    server.config.logger.warn(`REPOLENS_DEV_API_DELAY_MS=${env.REPOLENS_DEV_API_DELAY_MS}: /api requests are delayed`);
    (server.middlewares as { use: (h: Handler) => void }).use(handler);
  };
  return { name: "repolens-dev-api-delay", configureServer: install, configurePreviewServer: install };
}

/** The middleware itself, or null when no delay is configured. */
export function delayHandler(env: Record<string, string | undefined>): Handler | null {
  const ms = Number(env.REPOLENS_DEV_API_DELAY_MS ?? 0);
  if (!Number.isFinite(ms) || ms <= 0) return null;
  const match = env.REPOLENS_DEV_API_DELAY_MATCH ? new RegExp(env.REPOLENS_DEV_API_DELAY_MATCH) : null;
  return (req, _res, next) => {
    const url = req.url ?? "";
    if (url.startsWith("/api/") && (!match || match.test(url))) setTimeout(next, ms);
    else next();
  };
}
