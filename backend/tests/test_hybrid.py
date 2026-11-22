"""Hybrid search (Step 5 Part B): question terms, reciprocal rank fusion, and keyword search on the
fixture repo. No LLM."""

import pytest

from app import config
from app.db import pool
from app.qa.chunks import query_terms, search_words
from app.qa.embed import get_embedder
from app.qa.retrieve import _keyword, _vector, fuse, retrieve

# --- question terms (pure) -------------------------------------------------------------------


def test_terms_split_like_the_stored_search_words():
    assert query_terms("How does getUserById read the HTTPServer config?") == [
        "get", "user", "id", "getuserbyid", "read", "http", "server", "httpserver", "config"]
    # snake_case: the parts; the whole name with underscores is not a single lexeme
    assert query_terms("What calls _make_keys_list?") == ["calls", "make", "keys", "list"]


def test_terms_are_the_stored_words_of_the_same_identifier():
    class C:  # the three fields search_words reads
        path, qualified_name, text = "", "", "getUserById max_age"
    assert set(query_terms("getUserById max_age")) <= set(search_words(C).split())


def test_stop_words_one_letters_and_repeats_are_dropped():
    assert query_terms("How does it do it? Is it a token's age?") == ["token", "age"]
    assert query_terms("the a of to is") == []


def test_operator_characters_never_reach_the_tsquery():
    terms = query_terms("a & b | !c ' : * <-> (x) \\ \"y\" z:* send&receive")
    assert all(t.isalnum() and t.islower() or t.isdigit() for t in terms)
    assert terms == ["send", "receive"]


# --- fusion (pure) ---------------------------------------------------------------------------


def _rows(*ids):
    return [{"id": i, "distance": 0.1 * n} for n, i in enumerate(ids)]


def test_fusion_rewards_agreement_and_dedupes():
    got = fuse(_rows(1, 2, 3), _rows(3, 4), k=8, rrf_k=60)
    # 3 is in both lists; 1 is a first; 2 and 4 are both seconds at the same distance: lower id
    assert [r["id"] for r in got] == [3, 1, 2, 4]
    assert len({r["id"] for r in got}) == len(got)


def test_fusion_ties_prefer_the_better_rank_then_distance_then_id():
    # 1 and 5 each rank first in one list: same score, same best rank; 1 is nearer
    got = fuse([{"id": 5, "distance": 0.2}], [{"id": 1, "distance": 0.1}], k=8, rrf_k=60)
    assert [r["id"] for r in got] == [1, 5]
    got = fuse([{"id": 5, "distance": 0.1}], [{"id": 1, "distance": 0.1}], k=8, rrf_k=60)
    assert [r["id"] for r in got] == [1, 5]  # equal distance: lower id


def test_fusion_with_no_keyword_hits_is_the_vector_order_cut_to_k():
    assert [r["id"] for r in fuse(_rows(4, 2, 9, 7), [], k=3, rrf_k=60)] == [4, 2, 9]


# --- on the fixture repo (database) ----------------------------------------------------------


@pytest.fixture
def snapshot(client):
    body = client.post("/repos", json={"url": "https://github.com/example/sample"}).json()
    assert client.get(f"/snapshots/{body['snapshot_id']}/status").json()["status"] == "done"
    return body["snapshot_id"]


def _keyword_names(snapshot, question, include_tests=False):
    q = _vector(get_embedder().embed([question])[0])
    with pool().connection() as conn:
        rows = _keyword(conn, snapshot, q, query_terms(question), 16, include_tests)
    return [(r["qualified_name"], r["in_test"]) for r in rows]


def _snippets(r):
    return [(s.chunk_id, s.via) for s in r.snippets]


@pytest.mark.db
def test_hybrid_false_ignores_the_default_and_the_default_is_followed(snapshot, monkeypatch):
    q = "How is a user created?"
    monkeypatch.setattr(config, "QA_HYBRID", False)
    off = retrieve(snapshot, q)
    assert off.hybrid is False and off.summary()["hybrid"] is False
    monkeypatch.setattr(config, "QA_HYBRID", True)
    assert _snippets(retrieve(snapshot, q, hybrid=False)) == _snippets(off)
    assert retrieve(snapshot, q).hybrid is True


@pytest.mark.db
def test_keyword_search_finds_a_named_identifier_first(snapshot):
    names = _keyword_names(snapshot, "Where is create_user defined?")
    assert names[0][0] == "sample_app.service.create_user"
    got = retrieve(snapshot, "Where is create_user defined?", hybrid=True, expand=False)
    assert got.hybrid is True
    assert "sample_app.service.create_user" in [s.qualified_name for s in got.snippets]
    assert len(got.snippets) <= 8


@pytest.mark.db
def test_keyword_search_follows_the_test_code_rule(snapshot):
    q = "What does check_create_user check?"
    assert all(not in_test for _, in_test in _keyword_names(snapshot, q))
    assert ("tests.check_service.check_create_user", True) in _keyword_names(
        snapshot, q, include_tests=True)
    got = retrieve(snapshot, q, hybrid=True)
    assert not any(s.in_test for s in got.snippets)


@pytest.mark.db
def test_questions_with_operators_or_no_terms_do_not_fail(snapshot):
    for q in ["a & b | !c ' : * <-> (x)", "Is it?", "send&receive:*"]:
        got = retrieve(snapshot, q, hybrid=True, expand=True)
        assert got.snippets  # vector search still answers
