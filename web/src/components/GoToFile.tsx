// "Go to file": a dialog that finds a file or folder by name or path and opens it in the Explorer.
// Loaded on first use (AnalysisShell), so pages without it never fetch this code.

import { useQuery } from "@tanstack/react-query";
import { type KeyboardEvent, useDeferredValue, useEffect, useId, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { getGraph } from "../api";
import { useEscapeToClose } from "../escapeStack";
import {
  buildEntries,
  LANG_MARK,
  pieces,
  type Range,
  type SearchEntry,
  type SearchMatch,
  searchEntries,
} from "../fileSearch";
import { exploreHref, REVEAL } from "../links";
import { Icon } from "./Icon";

/** Settings of the Explorer that a result keeps (what is drawn, not where). */
const KEEP = ["guesses", "edges", "view"] as const;

export const SCOPE_NOTE = "Searches the Python, JavaScript and TypeScript files the analysis can open.";
export const TESTS_NOTE = "Opens with Tests & examples turned on.";

/** Where a result goes: the Explorer with the file selected (the same link as a citation chip) or
 * the folder opened. `tests=1` when the page already shows tests or the result is a test or
 * example (or not known yet), so it is always on the map; the Explorer's other settings stay. */
export function resultHref(
  snapshotId: number,
  entry: SearchEntry,
  page: { onExplorer: boolean; search: string },
): string {
  const current = new URLSearchParams(page.search);
  const pageTests = page.onExplorer && current.get("tests") === "1";
  const tests = pageTests || entry.test !== false;
  const ask = current.get("ask") === "1";
  let href: string;
  if (entry.kind === "file") {
    href = exploreHref(snapshotId, { fileId: entry.fileId!, tests, ask });
  } else {
    const params = new URLSearchParams({ level: "folder", root: entry.path });
    if (tests) params.set("tests", "1");
    if (ask) params.set("ask", "1");
    href = `/a/${snapshotId}/explore?${params}`;
  }
  if (!page.onExplorer) return href;
  const url = new URL(href, "http://x");
  for (const key of KEEP) {
    const value = current.get(key);
    if (value !== null) url.searchParams.set(key, value);
  }
  return url.pathname + url.search;
}

/** Turns on Tests & examples: the page hides tests and this result is one. */
function turnsOnTests(entry: SearchEntry, page: { onExplorer: boolean; search: string }): boolean {
  const pageTests = page.onExplorer && new URLSearchParams(page.search).get("tests") === "1";
  return !pageTests && entry.test === true;
}

export function GoToFile({ snapshotId, onClose }: { snapshotId: number; onClose: () => void }) {
  const location = useLocation();
  const navigate = useNavigate();
  const onExplorer = location.pathname.endsWith("/explore");
  const params = new URLSearchParams(location.search);
  // The same queries as the Explorer's own file list, so a list it already has is not fetched again.
  const showGuesses = onExplorer && params.get("guesses") === "1";
  const withTests = useQuery({
    queryKey: ["graph", snapshotId, true, showGuesses],
    queryFn: ({ signal }) => getGraph(snapshotId, { showTests: true, showGuesses }, signal),
    staleTime: Infinity,
  });
  const withoutTests = useQuery({
    queryKey: ["graph", snapshotId, false, showGuesses],
    queryFn: ({ signal }) => getGraph(snapshotId, { showTests: false, showGuesses }, signal),
    staleTime: Infinity,
  });
  const entries = useMemo(
    () => (withTests.data ? buildEntries(withTests.data.nodes, withoutTests.data?.nodes ?? null) : null),
    [withTests.data, withoutTests.data],
  );

  const [query, setQuery] = useState("");
  // The field shows each key at once; the list follows as a deferred render, which a faster next
  // key can interrupt (drawing 50 rows is most of a keystroke's cost on a slow PC, not matching).
  const shown = useDeferredValue(query);
  const [active, setActive] = useState(0);
  const result = useMemo(() => (entries ? searchEntries(entries, shown) : null), [entries, shown]);
  const matches = result?.matches ?? [];
  useEffect(() => setActive(0), [shown]);

  // A modal dialog: the page behind it is inert, focus stays inside. Esc goes through the shared
  // Escape handler (escapeStack), which closes only the top layer: this dialog. The native
  // "cancel" is then never left to act on its own.
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const closed = useRef(false);
  const close = () => {
    if (closed.current) return;
    closed.current = true;
    onClose();
  };
  // Focus goes back to what opened the dialog. A file opened from here then takes focus to its
  // panel heading (NodePanel), which runs after this clean-up.
  // Read at the first render, before the dialog takes focus (an effect may run twice in dev).
  const [opener] = useState(() =>
    document.activeElement instanceof HTMLElement ? document.activeElement : null,
  );
  useEffect(() => {
    const dialog = dialogRef.current;
    if (dialog && !dialog.open) dialog.showModal();
    inputRef.current?.focus();
    return () => {
      if (opener?.isConnected && opener !== document.body) opener.focus();
    };
  }, [opener]);
  useEscapeToClose(dialogRef, close);

  const listRef = useRef<HTMLUListElement>(null);
  useEffect(() => {
    listRef.current?.querySelector('[aria-selected="true"]')?.scrollIntoView?.({ block: "nearest" });
  }, [active, matches]);

  const page = { onExplorer, search: location.search };
  function open(match: SearchMatch) {
    const href = resultHref(snapshotId, match.entry, page);
    close();
    navigate(href, match.entry.kind === "file" ? { state: REVEAL } : undefined);
  }

  function onKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (matches.length === 0) return;
      const step = e.key === "ArrowDown" ? 1 : -1;
      setActive((i) => (i + step + matches.length) % matches.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      // The list may still show an earlier query: open the best match for what was typed.
      const match =
        shown === query ? matches[active] : entries ? searchEntries(entries, query, 1).matches[0] : undefined;
      if (match) open(match);
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault(); // the shortcut again: keep the browser's own Ctrl+K away
      e.currentTarget.select();
    }
  }

  const titleId = useId();
  const listId = useId();
  const noteId = useId();
  const optionId = (i: number) => `${listId}-${i}`;
  const activeMatch = matches[active];
  const note = activeMatch && turnsOnTests(activeMatch.entry, page) ? TESTS_NOTE : "";
  const loading = !entries && !withTests.error;
  const trimmed = shown.trim();

  return (
    <dialog
      ref={dialogRef}
      className="goto"
      aria-labelledby={titleId}
      onCancel={(e) => {
        e.preventDefault();
        close();
      }}
      // A click on the backdrop lands on the dialog itself (the content fills it).
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div className="goto-inner">
        <h2 id={titleId} className="visually-hidden">
          Go to file
        </h2>
        <div className="goto-field">
          <Icon name="search" />
          <input
            ref={inputRef}
            className="input goto-input"
            type="text"
            role="combobox"
            aria-autocomplete="list"
            aria-expanded={matches.length > 0}
            aria-controls={listId}
            aria-activedescendant={activeMatch ? optionId(active) : undefined}
            aria-describedby={noteId}
            aria-label="File or folder name, or a path"
            placeholder="File or folder name, or a path"
            // No browser or keyboard help in a file-name field: autofill, spelling, autocorrect,
            // capitals. (Windows' own typing suggestions are an OS setting; see DESIGN.md.)
            autoComplete="off"
            spellCheck={false}
            autoCorrect="off"
            autoCapitalize="off"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
          />
        </div>

        <div className="goto-results" aria-busy={loading || undefined}>
          <ul ref={listRef} id={listId} role="listbox" aria-label="Files and folders" className="goto-list">
            {matches.map((m, i) => (
              <ResultRow
                key={m.entry.path + m.entry.kind}
                id={optionId(i)}
                match={m}
                selected={i === active}
                onPick={() => open(m)}
                onHover={() => setActive(i)}
              />
            ))}
          </ul>
          {withTests.error && !entries ? (
            <div className="goto-message" role="alert">
              <p>Could not load the file list. {withTests.error.message}</p>
              <button type="button" className="button button-secondary button-small" onClick={() => withTests.refetch()}>
                Try again
              </button>
            </div>
          ) : loading ? (
            <div className="goto-message">
              <span className="visually-hidden">Loading files…</span>
              {[0, 1, 2].map((i) => (
                <span key={i} className="skeleton goto-skeleton" aria-hidden="true" />
              ))}
            </div>
          ) : trimmed === "" ? (
            <p className="goto-message caption">Type part of a file or folder name, or a path.</p>
          ) : result && result.total === 0 ? (
            <p className="goto-message" role="status">
              No files match “<span className="mono">{trimmed}</span>”
            </p>
          ) : result && result.total > matches.length ? (
            <p className="goto-message caption" role="status">
              {result.total - matches.length} more — keep typing
            </p>
          ) : null}
        </div>

        <div className="goto-footer caption">
          <p id={noteId} className="goto-note" aria-live="polite">
            {note || SCOPE_NOTE}
          </p>
          <p className="goto-keys" aria-hidden="true">
            <kbd>↑</kbd>
            <kbd>↓</kbd> move · <kbd>Enter</kbd> open · <kbd>Esc</kbd> close
          </p>
        </div>
      </div>
    </dialog>
  );
}

function ResultRow({
  id,
  match,
  selected,
  onPick,
  onHover,
}: {
  id: string;
  match: SearchMatch;
  selected: boolean;
  onPick: () => void;
  onHover: () => void;
}) {
  const { entry, ranges } = match;
  const { path, nameAt } = entry;
  return (
    <li
      id={id}
      role="option"
      aria-selected={selected}
      className="goto-row"
      title={path}
      // Keep focus in the field: the list is driven from there.
      onMouseDown={(e) => e.preventDefault()}
      onClick={onPick}
      onMouseMove={selected ? undefined : onHover}
    >
      {entry.kind === "folder" ? (
        <span className="goto-kind" aria-hidden="true">
          <Icon name="folder" size={14} />
        </span>
      ) : (
        <span className="graph-node-lang goto-lang" data-lang={entry.language ?? undefined} aria-hidden="true">
          {LANG_MARK[entry.language ?? ""] ?? "··"}
        </span>
      )}
      <span className="goto-text">
        <span className="goto-name mono">
          <Hits path={path} ranges={ranges} from={nameAt} to={path.length} />
        </span>
        {nameAt > 0 ? (
          // rtl so a long folder is cut at the start (the part next to the name stays); <bdi>
          // keeps the text itself in order
          <span className="goto-folder mono" dir="rtl">
            <bdi>
              <Hits path={path} ranges={ranges} from={0} to={nameAt - 1} />
            </bdi>
          </span>
        ) : null}
      </span>
      {entry.kind === "folder" ? <span className="visually-hidden">, folder</span> : null}
      {entry.test ? <span className="tag goto-tag">test or example</span> : null}
    </li>
  );
}

function Hits({ path, ranges, from, to }: { path: string; ranges: Range[]; from: number; to: number }) {
  return (
    <>
      {pieces(path, ranges, from, to).map((p, i) =>
        p.hit ? (
          <mark key={i} className="goto-hit">
            {p.text}
          </mark>
        ) : (
          <span key={i}>{p.text}</span>
        ),
      )}
    </>
  );
}

export default GoToFile;
