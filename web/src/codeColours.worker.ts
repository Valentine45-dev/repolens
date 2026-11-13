// The code-colouring worker: one long-lived highlighter, one request at a time (the page sends the
// next only after this one answers). Repo text is only ever tokenised here, never run or parsed
// as HTML; the answer is plain data ([role, text] runs).
import { colourLines, warmUp } from "./codeColoursCore";
import type { CodeLang } from "./codeRoles";

interface Scope {
  postMessage(message: unknown): void;
  onmessage: ((event: MessageEvent<{ id: number; code?: string; lang: CodeLang; warm?: boolean }>) => void) | null;
}
const scope = self as unknown as Scope;

scope.onmessage = async (event) => {
  const { id, code, lang, warm } = event.data;
  try {
    if (warm) {
      await warmUp(lang);
      scope.postMessage({ id, lines: [] });
      return;
    }
    scope.postMessage({ id, lines: await colourLines(code ?? "", lang) });
  } catch (err) {
    scope.postMessage({ id, error: err instanceof Error ? err.message : String(err) });
  }
};
