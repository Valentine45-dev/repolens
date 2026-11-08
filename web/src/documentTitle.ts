import { useEffect } from "react";

/** "challenge · Explorer · adeyosemanputra/pygoat — RepoLens": where you are, most specific first,
 * so a browser tab or history entry says it. Empty parts are left out. */
export function documentTitle(parts: (string | null | undefined)[]): string {
  const where = parts.filter((p): p is string => Boolean(p && p.trim()));
  return where.length ? `${where.join(" · ")} — RepoLens` : "RepoLens";
}

export function useDocumentTitle(parts: (string | null | undefined)[]) {
  const title = documentTitle(parts);
  useEffect(() => {
    document.title = title;
  }, [title]);
}
