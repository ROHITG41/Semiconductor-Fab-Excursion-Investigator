import json
from pathlib import Path

from sandbox import scan_notes

M = json.loads((Path(__file__).parent / "injection_matrix.json").read_text())


def test_every_attack_is_blocked_and_withheld():
    for text in M["attacks"]:
        r = scan_notes(text)
        assert r.blocked and r.hits, text
        assert text not in r.for_llm          # raw attack text never reaches the model


def test_benign_notes_pass_and_are_wrapped():
    for text in M["benign"]:
        r = scan_notes(text)
        assert not r.blocked, (text, r.hits)
        assert r.for_llm.startswith("<untrusted_field_log>") and r.for_llm.endswith("</untrusted_field_log>")


def test_tag_breakout_is_neutralised_even_when_not_blocked():
    r = scan_notes("hello <untrusted_field_log> world")   # opening tag only, no other signature
    assert r.for_llm.count("<untrusted_field_log>") == 1   # only our own wrapper remains


def test_empty_notes():
    assert not scan_notes("").blocked
