# Test fixtures: deliberately broken and vulnerable code

Everything under this folder is **input for the tests**, not part of RepoLens. The problems in
these files are on purpose: each one is something a test expects RepoLens to find, report or
cope with. **Do not fix, reformat or lint-clean these files.** Tests check exact line numbers,
so even moving a line breaks them.

Nothing here is ever executed, imported or installed. RepoLens only parses source code; it
never runs the code it analyses.

| Folder | What it is | Deliberate problems |
|---|---|---|
| `sample_repo/` | A small fake repository (Python + JS/TS) that the ingestion tests analyse in place of a real clone. | `sample_app/broken.py` imports modules that do not exist (unresolved imports must be reported, not crash the parser); `web/src/app.ts` imports `./missing`; `settings.py` holds a fake password (`fixture-not-a-real-password`) for the secret redaction tests; `models.py` has a nested class method whose first parameter is `cls`, not `self`; `tests/check_service.py` and `math.spec.ts` are test-like files for the "exclude tests" filters. |
| `detectors/` | Positive and negative samples for each detector rule. | `*_positive.*` files contain `eval`, `exec`, shell commands, SQL built from strings, `innerHTML` and bare `except` on lines marked `expect: <rule>`; `*_negative.*` files contain safe look-alikes that must not be reported. |

## Editor warnings

VS Code would normally underline these problems. The committed editor settings silence that
for this folder only, without touching the files:

- `.vscode/settings.json` (repository root): Pylance shows no diagnostics for this folder, and
  the `.ts`/`.tsx` files in `sample_repo/` open as plain text (their `tsconfig.json` is part of
  the fixture, so it cannot be changed).
- `backend/pyproject.toml`, `[tool.pyright] ignore`: the same for Pyright, and for Pylance when
  `backend/` is opened on its own.
- `tsconfig.json` in this folder: turns off type checking (`noCheck`) for `detectors/`.

The detector **evaluation** fixtures (`eval/detector_fixtures/`) are a separate, labelled set
used to score RepoLens against Bandit and Semgrep; they are deliberately vulnerable too.
