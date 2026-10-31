"""cited_sentence_rate: how many sentences of saved Q&A answers carry a valid citation.

    uv run --project backend python eval/score_claims.py eval/results/<qa results>.json \\
        --label "own PC, v1-submitted"

WHAT THIS MEASURES: whether sentences CARRY citations. It does NOT measure whether a citation
supports the sentence it is attached to; that needs a reader (human or model) and is not done here.

Input: a Q&A results file written by eval/smoke_qa.py (questions[].answer, .citations, .status).
No LLM, no database, no network.

Definition of "valid citation": present in the result's validated citations list. The product
removes every citation that did not lie inside a snippet it sent before the answer is stored, so
a citation found in the answer text counts as valid when its (path, start, end) is in that list.

Sentence splitting rules (fixed before the script was run on any results):
1. Fenced code blocks (``` ... ```) are removed whole. They hold code, not claims.
2. The rest is read line by line. Blank lines, headings (lines starting with #) and empty bullets
   (a list marker, optionally with bold markers or whitespace, and no words) are skipped. List
   markers ("- ", "* ", "1. ") and leading bold/italic markers are stripped.
3. Inline code spans (`...`) are not split inside: a "." inside backticks never ends a sentence.
4. A sentence ends at ".", "!" or "?" followed by whitespace and then an upper-case letter, a
   backtick, an asterisk, an opening bracket or a quote, or by the end of the line. "e.g.",
   "i.e.", "etc.", "vs." and a single-letter abbreviation do not end a sentence.
5. A fragment that is only a citation (for example "(lib/x.js:1-9).") belongs to the sentence
   before it on the same line. Any other fragment with fewer than 3 words (after removing code
   spans and citations) is dropped as not a claim ("Yes.", "Note:").
6. The citation pattern is the product's own (app/qa/citations.py): path:N or path:N-M, with a
   hyphen, en dash or em dash, optional "L", optionally in backticks.
7. A sentence "has a valid citation" if at least one citation in it is in the validated list.
8. Answers with no sentences (empty) are listed with 0 sentences and are left out of the rate.
   Everything else counts, including identity and "could not find" answers, which carry no
   citations by design; the overall rate is also given without them ("claim answers").
"""

import argparse
import json
import re
from pathlib import Path

from runinfo import ROOT, run_info, save_results

CITATION = re.compile(
    r"(?P<tick>`?)(?P<path>(?:\./)?[\w@+\-./]*\w\.\w+)"
    r":L?(?P<start>\d+)(?:\s*[-–—]\s*L?(?P<end>\d+))?(?P=tick)"
)
FENCE = re.compile(r"```.*?```", re.S)
CODE_SPAN = re.compile(r"`[^`\n]*`")
ABBREV = re.compile(r"(?:\be\.g|\bi\.e|\betc|\bvs|\b[A-Za-z])\.$", re.I)
END = re.compile(r"[.!?](?=\s+[A-Z`*(\"'“]|\s*$)")
BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
EMPTY_BULLET = re.compile(r"^\s*(?:[-*+]|\d+[.)])?\s*[*_\s]*$")


def _mask_spans(text: str) -> str:
    """Same length, with code-span contents blanked so punctuation inside never splits."""
    return CODE_SPAN.sub(lambda m: "`" + "x" * (len(m[0]) - 2) + "`", text)


def split_sentences(answer: str) -> list[str]:
    sentences: list[str] = []
    for raw in FENCE.sub("\n", answer).splitlines():
        if not raw.strip() or raw.lstrip().startswith("#") or EMPTY_BULLET.match(raw):
            continue
        line = BULLET.sub("", raw).strip()
        line = re.sub(r"^[*_]+", "", line)
        masked = _mask_spans(line)
        parts, start = [], 0
        for m in END.finditer(masked):
            if ABBREV.search(masked[start:m.end()]):
                continue
            parts.append(line[start:m.end()].strip())
            start = m.end()
        if line[start:].strip():
            parts.append(line[start:].strip())
        kept: list[str] = []
        for p in parts:
            bare = CITATION.sub("", p)
            bare = re.sub(r"[()\[\].,;:\s`*_]+", " ", bare).strip()
            if not bare and kept:
                kept[-1] += " " + p  # citation-only fragment belongs to the sentence before
            elif len(re.findall(r"[A-Za-z]{2,}", CODE_SPAN.sub("", CITATION.sub("", p)))) >= 3:
                kept.append(p)
        sentences.extend(kept)
    return sentences


def valid_set(citations: list[str]) -> set[tuple[str, int, int]]:
    out = set()
    for c in citations:
        m = re.fullmatch(r"(.+):(\d+)-(\d+)", c)
        if m:
            out.add((m[1], int(m[2]), int(m[3])))
    return out


def score_answer(row: dict) -> dict:
    valid = valid_set(row["citations"])
    sentences = split_sentences(row["answer"])
    cited = []
    for s in sentences:
        found = {(m["path"].removeprefix("./"), int(m["start"]), int(m["end"] or m["start"]))
                 for m in CITATION.finditer(s)}
        cited.append(bool(found & valid))
    n = len(sentences)
    return {"id": row["id"], "type": row.get("type"), "status": row["status"], "sentences": n,
            "cited_sentences": sum(cited), "rate": round(sum(cited) / n, 3) if n else None,
            "uncited": [s[:160] for s, c in zip(sentences, cited) if not c]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("results", type=Path)
    parser.add_argument("--label", required=True, help="e.g. 'old laptop, pre-fix'")
    args = parser.parse_args()

    data = json.loads(args.results.read_text(encoding="utf-8"))
    rows = [score_answer(r) for r in data["questions"]]
    scored = [r for r in rows if r["sentences"]]
    claim = [r for r in scored if r["cited_sentences"] or r["type"] in ("answerable",)]
    total = sum(r["sentences"] for r in scored)
    cited = sum(r["cited_sentences"] for r in scored)
    c_total = sum(r["sentences"] for r in claim)
    c_cited = sum(r["cited_sentences"] for r in claim)
    summary = {
        "overall": {"sentences": total, "cited_sentences": cited,
                    "rate": round(cited / total, 3) if total else None},
        "claim_answers_only": {"answers": len(claim), "sentences": c_total,
                               "cited_sentences": c_cited,
                               "rate": round(c_cited / c_total, 3) if c_total else None,
                               "note": "answerable questions only; leaves out identity, "
                                       "injection-fixture and the unanswerable traps"},
    }
    print(f"{args.label} | {args.results.name}")
    print("NOTE: this measures whether sentences carry citations, not whether citations "
          "support them.")
    print(f"{'id':<10}{'status':<11}{'sentences':>9}{'cited':>7}{'rate':>7}")
    for r in rows:
        rate = "-" if r["rate"] is None else f"{r['rate']:.2f}"
        print(f"{str(r['id']):<10}{r['status']:<11}{r['sentences']:>9}{r['cited_sentences']:>7}"
              f"{rate:>7}")
    o, c = summary["overall"], summary["claim_answers_only"]
    print(f"overall {o['cited_sentences']}/{o['sentences']} = {o['rate']}")
    print(f"answerable questions only {c['cited_sentences']}/{c['sentences']} = {c['rate']}")
    info = run_info(llm_used=False)
    info["notes"] = f"{args.label}; input {args.results.resolve().relative_to(ROOT).as_posix()}"
    results = {"label": args.label, "input": args.results.name,
               "measures": "whether sentences carry a valid citation, not whether the citation "
                           "supports the sentence",
               "summary": summary, "answers": rows}
    print("saved", save_results("cited_sentence_rate", info, results))


if __name__ == "__main__":
    main()
