# V2 evaluation design: metrics and run protocol (§5, §6)

Copied from the project's v2 evaluation design document (sections 5 and 6 only; no question
content). `eval/locked_metrics.py` and `eval/locked_eval.py` implement these sections; the
choices the text leaves open are written at the top of `eval/locked_metrics.py`.

## §5 Metrics

**Retrieval** (per question, per configuration): applies to code_how, locate and purpose only;
graph, unanswerable, false_premise and injection are excluded from retrieval metrics.
- code_hit@k: a retrieved chunk overlaps an expected `source: code` range — headline metric,
  computed over code_how + locate, unchanged from v1.
- doc_hit@k: the same for `source: doc` ranges, reported separately (mainly purpose).
- Never report "any source found" as the headline.
- Configurations: A top-8 search, B top-16 search, C top-8 + graph expansion; later D hybrid
  (keyword + vector), E docs pool on/off.
- Comparisons are paired: per-question wins/losses between two configs plus an exact sign test
  (McNemar) p-value; small differences are called not conclusive.

**Graph questions:** record routed_to (graph | ai). Score exact match of the returned file set
against expected_files, plus precision/recall of the set. Report the routing rate separately: a
structural question that falls through to the AI is a routing miss even if the AI answer is
right.

**Q&A:**
- answered_correct_file — answer cites an expected file (code or doc as appropriate).
- citation_validity — every citation's range lies inside a snippet that was sent (does not check
  that the cited lines support the claim).
- cited_sentence_rate — share of answer sentences (outside code spans) that carry at least one
  valid citation, computed offline from saved results.
- faithful_human — a human judges, per answer, whether every claim is supported by the cited
  lines (yes / partly / no), on all locked-set answers, blind to configuration where possible;
  the only metric that may be called "faithfulness".
- unanswerable_ok — says it could not find it, with no invented claims. Revised false-premise
  rule: a correct rejection ("it signs, it does not encrypt") passes even with citations, as long
  as no citation supports a false claim. Write this rule into the eval script and freeze it
  before the locked run.
- Record latency and tokens.

## §6 Run protocol (every run)
1. Questions, labels and scoring rules committed (locked set: hash only) before the run.
2. Record commit SHA, machine (name, CPU model, RAM, Python version), embedding model and
   revision, LLM model, effort, thinking setting, prompt version, retrieval settings, doc-pool
   settings, MAX_ANALYSIS_S.
3. Answer cache off. One run per configuration.
4. Repeat rule: on tuning runs the first result counts; any retry is listed separately as
   information. Locked runs are run twice, both passes reported along with their agreement
   rate. Never re-run only the failures.
5. Keep every failure; report negative and null results.
6. Locked set: one run (two passes) per released version only, on the fixed eval machine.

## Decisions taken with the owner before the freeze (21 Nov 2026)
1. An AI-type question the router sends to the graph scores `answered_correct_file = false`
   (only validated citations count); the route is reported next to it.
2. unanswerable / false_premise: automatic pass = the "could not find" answer with zero
   citations in the model's raw output, counted before the server drops invalid ones (revised
   by the owner, 21 Nov, after the tuning check: any attempted citation goes to the judge).
   Every other answer goes to the human sheet with two questions: does it reject the
   premise (or say it could not find it), and does any citation support a false claim. Pass =
   rejects and no citation supports a false claim. The summary shows pass / fail / awaiting human.
3. A graph question answered by the AI route: the returned file set is the set of paths of its
   validated citations. The headline is over all graph questions; a graph-routed-only line is
   shown next to it.
4. Set precision = |R∩E| / |R| and recall = |R∩E| / |E|; when the denominator is empty the value
   is 1.0 if both sets are empty and 0.0 otherwise.
5. citation_validity (headline) = share of AI answers with no dropped citation (BASELINE-v1's
   definition); citation-level valid / (valid + dropped) is reported too.
6. Agreement between the two passes: per metric, the share of questions with the same outcome in
   both passes (questions awaiting a human verdict in either pass are left out and counted).
7. Spend guard: a pass is estimated before it runs (input tokens from the real prompts, 700
   output tokens per AI answer) and refused above $1; during a pass, a call whose worst case
   (input + LLM_MAX_TOKENS) would take the pass over $1 stops it and the pass is void. Prices are
   arguments, taken from the provider's pricing page on the day of the run.
8. Freeze: `eval/locked/scorer.sha256` lists the hashes of the scoring code. A locked run refuses
   if a hash differs, if tracked files are dirty, or if the question file's SHA-256 differs from
   `eval/locked/v2.0.sha256`. For v2.1 the only allowed runner change is new retrieval
   configurations, recorded with their diff.
9. Graph questions are scored against `expected_files_with_tests`: the default graph answer
   lists test files that depend on the target (tagged "test"); only the target lookup prefers
   non-test files.
