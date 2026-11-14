# Go to file (`feat/goto-file`)

Evidence for the "Go to file" dialog: a header button ("Go to file", `Ctrl K`), Ctrl+K / Cmd+K and
`/` (never while typing in a field), a search over every file the panel can open plus their
folders, and opening a result with the same link a citation chip uses.

Captured headless in Edge (throwaway profile, never a window shown to the owner) with
`eval/goto_file_evidence.mjs`, against the branch's build on :5173 and the real API. Keys are real
key events (`Input.dispatchKeyEvent`), text is typed with `Input.insertText`. **$0 API spend**: only
the status, graph, findings and file endpoints are called; nothing is asked.

```
node eval/goto_file_evidence.mjs --base http://127.0.0.1:5173 --out DIR --theme light|dark [--width 1366|1920]
```

Each run writes `<theme>-<width>.json` (DOM state after every step, and the checks below) and one
screenshot per step. Runs here: light 1366, dark 1366, light 1920 (for the overflow check).

## Screenshots (psf/black, snapshot 7; redash, snapshot 13)
| Step | What it shows |
|---|---|
| 1-header | The Explorer with tests off; the "Go to file" button left of Ask |
| 2-empty-query | Ctrl+K: the dialog before anything is typed (a hint, never a blank box) |
| 3-results-trans | "trans": `src/black/trans.py`, then `tests/test_trans.py` tagged "test or example"; matched characters on the highlighter |
| 4-hidden-test-file | "test_black": `tests/test_black.py`, hidden on the map, found and tagged; the footer says "Opens with Tests & examples turned on." |
| 5-empty-state | "zzqx": `No files match "zzqx"` |
| 6-opened-test-file | Enter: the map opens on `tests/` with Tests & examples checked, the file selected, the panel on its Code tab, focus on the panel heading |
| 7-redash-list | The largest analysis here (970 files + 165 folders), "index": 50 long rows; the list scrolls down, nothing sideways |

## Checks (all three runs passed every one)
| Check | Result |
|---|---|
| Home loads the dialog chunk / any graph list | no / no |
| The Explorer loads the dialog chunk or the list with tests before the dialog is opened | no / no |
| "/" with focus in Findings' "Path starts with" field | no dialog; the field gets the "/" |
| Esc with the file panel open behind the dialog | the dialog closes, the panel stays (`node=997`), focus back on the button |
| Hidden test file opened | `?node=997&tests=1`, Tests & examples checked, Code tab, code shown |
| Ctrl+K on Findings, then `src/black/trans.py` + Enter | `/a/7/explore?node=971`, Code tab |
| Sideways overflow, 2 rows (black) and 50 long rows (redash), 1366 light/dark and 1920 | none: the field, every row and every tag end inside the 640px dialog; the 50-row list shows a vertical scrollbar |

## Timings (eval PC, headless Edge)
- First open on black: dialog shown after 0.7-1.3 s (dialog chunk); the file list ready after
  1.5-4.4 s. Resource Timing of the list request: 0.65-3.0 s waiting for the server, under 0.6 s
  download. The server is the slow part, and it varies with what else the API is doing (the map
  views it is computing at the same time). A later open reuses both lists.
- Keystrokes on redash, in the page: the field's own update 1.5-11 ms; the list's DOM update (a
  deferred render the next key can interrupt) 8-114 ms. Matching is ~2-3 ms; drawing up to 50 rows
  is the rest.

## Two problems in earlier runs, and what they were
- **A light screenshot with the field's border and the tags cut off on the right, and no
  scrollbar** (many "trans" results). Real, and theme-independent: the dialog's content box was a
  flex item with the default `min-width: auto`, so a long row made it as wide as that row's unshrunk
  text; the field, the tags and the list's scrollbar were pushed past the dialog's right edge and
  clipped. Fixed (`.goto-inner { min-width: 0 }`, commit `03e742e`); the measured overflow check above
  now runs on every evidence pass.
- **Dark run: ~22 s for the first file list, then the Findings step did not open the file.**
  - *The Findings step* was the evidence script, not the app. It waited for "an input exists and
    no disabled search button", which `index.html`'s Findings placeholder satisfied at once (it has
    a path field and had no search button). The script focused the placeholder's field, React then
    replaced the page, and the keys arrived before the analysis status had loaded (the shortcut
    listens only from then on). Fixed in the script (waits for the real Findings table, checks focus
    is in the real field, fails loudly on any timeout) and in the page (the placeholders now carry
    the real button, disabled).
  - *The 22 s* was not reproduced. That run overlapped the backend test suite (19 minutes, same
    Postgres container) on this 8 GB PC. Re-running the suite as load and timing the same request
    80 times over five minutes gave at most 0.86 s (free RAM ~950 MB). The old script did not
    record where the time went (its waits also returned silently on timeout). It now records the list
    request's Resource Timing, so a repeat will show whether the server or the page was slow. The
    dialog shows its loading rows meanwhile.

## Not checked here
The browsers' own shortcuts and the OS text suggestions: synthetic key events never reach the
browser's chrome, and Windows draws its typing-suggestion bubble itself. Whether Firefox's Ctrl+K
(web search) or Quick Find on `/` can win over the page, and whether the suggestion bubble still
appears with `autocomplete/spellcheck/autocorrect/autocapitalize` off, need the owner's real
Firefox and Chrome. On this PC, Windows' "Show text suggestions when typing on the physical
keyboard" is on (`HKCU\Software\Microsoft\Input\Settings\EnableHwkbTextPrediction = 1`).
