"""How long the embed stage takes for one analysed snapshot, test and non-test chunks apart.

    uv run --project backend --env-file .env python eval/embed_timing.py --snapshot 83

Rebuilds the chunks exactly as the pipeline's embed stage does (stored redacted files ->
parse -> build_chunks) and embeds them with the configured model in the same batches, without
writing anything. Run it with nothing else using the CPU (stop the API first: it also holds a
copy of the model). Prints and saves chunk counts, tokens and seconds per group.
"""

import argparse
import time

from runinfo import header, run_info, save_results  # also puts backend/ on sys.path

from app import db  # noqa: E402
from app.ingest.pipeline import parse_file  # noqa: E402
from app.paths import is_test_path  # noqa: E402
from app.qa.chunks import build_chunks  # noqa: E402
from app.qa.embed import get_embedder  # noqa: E402

STEP = 256  # chunks per embed call, as in pipeline.store_chunks


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--snapshot", type=int, required=True)
    args = parser.parse_args()

    db.open_pool()
    with db.pool().connection() as conn:
        files = conn.execute(
            "SELECT path, language, content FROM files WHERE snapshot_id = %s"
            " AND language IN ('python', 'javascript', 'typescript') ORDER BY path",
            (args.snapshot,),
        ).fetchall()
        url = conn.execute(
            "SELECT r.url, s.commit_sha FROM snapshots s JOIN repos r ON r.id = s.repo_id"
            " WHERE s.id = %s", (args.snapshot,),
        ).fetchone()

    t = time.monotonic()
    embedder = get_embedder()
    load_s = time.monotonic() - t

    t = time.monotonic()
    chunks = []
    for f in files:
        result = parse_file(f["path"], f["language"], f["content"])
        chunks += build_chunks(f["path"], f["content"], result.symbols, embedder.count_tokens,
                               embedder.max_tokens)
    build_s = time.monotonic() - t

    groups = {"non_test": [c for c in chunks if not is_test_path(c.path)],
              "test": [c for c in chunks if is_test_path(c.path)]}
    out = {"snapshot": args.snapshot, "repo": url["url"], "commit": url["commit_sha"],
           "files": len(files),
           "test_files": sum(is_test_path(f["path"]) for f in files),
           "model_load_s": round(load_s, 1), "parse_and_chunk_s": round(build_s, 1),
           "groups": {}}
    for name, group in groups.items():
        t = time.monotonic()
        for i in range(0, len(group), STEP):
            embedder.embed([c.embed_text for c in group[i:i + STEP]])
        secs = time.monotonic() - t
        out["groups"][name] = {
            "chunks": len(group),
            "tokens": sum(c.token_count for c in group),
            "embed_s": round(secs, 1),
            "chunks_per_s": round(len(group) / secs, 1) if secs else None,
        }
    out["total_embed_s"] = round(sum(g["embed_s"] for g in out["groups"].values()), 1)

    info = run_info(llm_used=False)
    print(header(info))
    print(out)
    print("saved", save_results("embed_timing", info, out))


if __name__ == "__main__":
    main()
