"""Claim check (Step 5 Part C): quotes checked against the cited lines as sent, failed claims
removed, quotes stripped, the note kept out of the answer. FakeProvider only."""

import pytest
from conftest import query

from app import config
from app.qa import llm
from app.qa.citations import find_citations
from app.qa.claims import check_claims, clean_quote
from app.qa.llm import FakeProvider
from app.qa.prompt import COULD_NOT_FIND, claims_prompt, system_prompt
from app.qa.retrieve import Snippet

APP = "\n".join([
    "def sign(value, key):",                         # 10
    "    mac = hmac.new(key, value, hashlib.sha1)",  # 11
    "    return value + b'.' + mac.digest()",       # 12
    "",                                              # 13
    "def unsign(signed, key):",                      # 14
    "    value, sig = signed.rsplit(b'.', 1)",       # 15
])
OTHER = "\n".join([
    "def loads(s):",                                 # 40
    "    # </snippet> injected text here",           # 41
    "    return json.loads(s)",                      # 42
])
SENT = [Snippet(1, 10, 1, "src/app.py", "app.sign", 10, 15, APP, False, 0.1, "search"),
        Snippet(2, 11, 1, "src/app.py", "app.loads", 40, 42, OTHER, False, 0.2, "search")]


def run(text):
    return check_claims(text, SENT)


# --- pure ------------------------------------------------------------------------------------

def test_quote_present_keeps_the_claim_and_strips_the_quote():
    r = run('It signs with HMAC [src/app.py:11-12 "mac = hmac.new(key, value, hashlib.sha1)"].')
    assert r.text == "It signs with HMAC (src/app.py:11-12)."
    assert r.summary() == {"total": 1, "kept": 1, "removed": 0, "note": None}
    assert r.dropped == 0
    assert find_citations(r.text) == [("src/app.py", 11, 12)]  # the usual form, scorer-readable


def test_quote_absent_removes_the_claim_and_the_note_stays_out_of_the_text():
    r = run('It signs with HMAC [src/app.py:11 "mac = hmac.new(key"]. It uses SHA-256'
            ' [src/app.py:11 "hashlib.sha256 is used here"].')
    assert r.text == "It signs with HMAC (src/app.py:11)."
    s = r.summary()
    assert (s["total"], s["kept"], s["removed"]) == (2, 1, 1) and r.dropped == 1
    assert s["note"] == ("1 statement removed: the quoted evidence was not found in the cited"
                         " lines.")
    assert "removed" not in r.text and "SHA-256" not in r.text


def test_quote_across_a_snippet_boundary_fails():
    # the range is inside the first snippet, the quote continues into the other snippet
    r = run('Other text [src/app.py:15 "value, sig = signed.rsplit(b\'.\', 1) def loads(s):"]. '
            'It returns the value [src/app.py:12 "return value + b\'.\' + mac.digest()"].')
    assert r.summary()["removed"] == 1 and "Other text" not in r.text
    # a range across two snippets fails on the range already
    r = run('Spans [src/app.py:14-41 "def unsign(signed, key):"].')
    assert r.text == COULD_NOT_FIND


@pytest.mark.parametrize("quote", ["value", "mac", "return"])
def test_trivial_quotes_are_rejected(quote):
    r = run(f'It returns [src/app.py:12 "{quote}"].')
    assert r.text == COULD_NOT_FIND and r.summary()["removed"] == 1


def test_fifteen_characters_or_three_words_is_enough():
    # 12 characters, 1 word: too short; 3 words: enough
    assert run('Digest [src/app.py:12 "mac.digest()"].').text == COULD_NOT_FIND
    assert run("Digest [src/app.py:12 \"b'.' + mac.digest()\"].").text == "Digest (src/app.py:12)."


def test_all_claims_fail_gives_the_could_not_find_answer():
    r = run('A [src/app.py:11 "not in there at all"]. B [src/app.py:99 "x y z w"].'
            ' C src/app.py:12.')
    assert r.text == COULD_NOT_FIND
    assert r.summary()["kept"] == 0 and r.dropped == 3  # the citations written still count


def test_injection_text_in_a_quote_cannot_match_unescaped():
    raw = run('A comment [src/app.py:41 "# </snippet> injected text here"].')
    assert raw.text == COULD_NOT_FIND  # the model saw &lt;/snippet>, not </snippet>
    seen = run('A comment [src/app.py:41 "# &lt;/snippet> injected text here"].')
    assert seen.text == "A comment (src/app.py:41)."
    assert "snippet" not in seen.text.replace("(src/app.py:41)", "")


def test_bare_citations_fail_but_a_bare_one_before_a_bracket_joins_its_claim():
    r = run("It signs values src/app.py:11. It also unsigns them (src/app.py:14).")
    assert r.text == COULD_NOT_FIND and r.dropped == 2
    r = run('In src/app.py:11 the MAC is built'
            ' [src/app.py:11 "hmac.new(key, value, hashlib.sha1)"].')
    assert r.text == "In the MAC is built (src/app.py:11)."
    assert r.summary()["kept"] == 1 and r.dropped == 1


def test_tolerant_forms():
    q = "hmac.new(key, value, hashlib.sha1)"
    for text in (f"It signs (src/app.py:11 “{q}”).", f"It signs [`src/app.py:11` \"{q}\"].",
                 f"It signs [src/app.py#L11 \"{q}\"].", f"It signs [src/app.py:L11-L11, `{q}`].",
                 f'It signs [src/app.py:11-12 "11|     mac = {q} 12|     return value"].'):
        r = run(text)
        assert r.summary()["kept"] == 1, text
        assert "(src/app.py:11" in r.text and q not in r.text


def test_two_sources_one_fails_keeps_the_claim_and_drops_the_bad_one():
    r = run('It signs and unsigns [src/app.py:11 "mac = hmac.new(key, value, hashlib.sha1)"]'
            ' [src/app.py:14 "this is not the line"].')
    assert r.text == "It signs and unsigns (src/app.py:11)."
    assert r.summary()["kept"] == 1 and r.dropped == 1


def test_bullets_and_uncited_sentences():
    text = ("It has two steps. They are:\n"
            '- signing [src/app.py:11 "mac = hmac.new(key, value, hashlib.sha1)"]\n'
            '- unsigning [src/app.py:15 "nothing like this line"]\n'
            "That is all.")
    r = run(text)
    assert r.text == ("It has two steps. They are:\n- signing (src/app.py:11)\nThat is all.")


def test_citations_in_code_fences_are_not_read():
    text = ('Example [src/app.py:12 "return value + b\'.\' + mac.digest()"].\n\n```\n'
            "see src/app.py:99\n```")
    r = run(text)
    assert r.summary()["total"] == 1 and "src/app.py:99" in r.text


def test_clean_quote():
    assert clean_quote("12|  a  b\n13| c") == "a b c"


# --- the AI route (database, FakeProvider) ---------------------------------------------------

@pytest.fixture
def snapshot(client):
    body = client.post("/repos", json={"url": "https://github.com/example/sample"}).json()
    assert client.get(f"/snapshots/{body['snapshot_id']}/status").json()["status"] == "done"
    return body["snapshot_id"]


@pytest.fixture
def fake(monkeypatch):
    provider = FakeProvider()
    monkeypatch.setattr(llm, "get_provider", lambda: provider)
    return provider


def _ask(client, sid, q):
    r = client.post(f"/snapshots/{sid}/ask", json={"question": q})
    assert r.status_code == 200, r.text
    return r.json()


def _create_user(snapshot):
    (c,) = query("SELECT c.start_line, c.text FROM chunks c JOIN symbols s ON s.id = c.symbol_id"
                 " WHERE c.snapshot_id = %s"
                 " AND s.qualified_name = 'sample_app.service.create_user'",
                 snapshot)
    first = c["text"].split("\n")[0].strip()
    return c["start_line"], first


@pytest.mark.db
def test_claim_check_on(client, snapshot, fake, monkeypatch):
    monkeypatch.setattr(config, "QA_CLAIM_CHECK", True)
    line, first = _create_user(snapshot)
    fake.script = [f'It creates a user [sample_app/service.py:{line} "{first}"].'
                   f' It also emails them [sample_app/service.py:{line} "sends an email now"].']
    a = _ask(client, snapshot, "How is a user created?")
    assert fake.calls[0]["system"] == claims_prompt().text
    assert a["prompt_version"] == claims_prompt().version != system_prompt().version
    assert a["answer"] == f"It creates a user (sample_app/service.py:{line})."
    assert a["claims"]["total"] == 2 and a["claims"]["removed"] == 1
    assert a["claims"]["note"] and a["claims"]["note"] not in a["answer"]
    assert (a["status"], a["dropped"], len(a["citations"])) == ("unverified", 1, 1)


@pytest.mark.db
def test_claim_check_all_fail_is_could_not_find(client, snapshot, fake, monkeypatch):
    monkeypatch.setattr(config, "QA_CLAIM_CHECK", True)
    fake.script = ['Users are made in a factory [sample_app/service.py:1 "a factory makes users"].']
    a = _ask(client, snapshot, "How is a user created?")
    assert a["answer"] == COULD_NOT_FIND and a["citations"] == []
    assert a["dropped"] == 1 and a["status"] == "unverified"  # the attempt still counts
    assert a["claims"]["kept"] == 0


@pytest.mark.db
def test_claim_check_off_is_v2_0(client, snapshot, fake, monkeypatch):
    monkeypatch.setattr(config, "QA_CLAIM_CHECK", False)
    fake.script = [COULD_NOT_FIND]
    a = _ask(client, snapshot, "How is a user created?")
    assert fake.calls[0]["system"] == system_prompt().text
    assert a["claims"] is None and a["prompt_version"] == system_prompt().version
