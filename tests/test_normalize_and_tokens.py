"""Normalisation and the token finder - the part that must not need a model."""

from __future__ import annotations

from threadgate.normalize import find_span, normalize_text
from threadgate.pipeline import email_to_text
from threadgate.tokens import find_tokens, unique_accounts


def _tokens_for(case):
    nt = normalize_text(email_to_text(case["email"]))
    return nt, find_tokens(nt)


def test_zero_width_spaces_are_removed_and_offsets_still_map():
    raw = "A/C 5010\u200b0234\u200b5598\u200b21"
    nt = normalize_text(raw)
    assert nt.text == "A/C 50100234559821"
    start, end = nt.text.index("50100234559821"), nt.text.index("50100234559821") + 14
    r0, r1 = nt.to_raw_span(start, end)
    assert raw[r0:r1].replace("\u200b", "") == "50100234559821"


def test_non_breaking_hyphen_folds_to_ascii():
    nt = normalize_text("A/C 5010\u20110234\u20115598\u201121")
    assert nt.text == "A/C 5010-0234-5598-21"


def test_fullwidth_digits_fold():
    nt = normalize_text("A/C \uff15\uff10\uff11\uff10\uff10\uff12\uff13\uff14\uff15\uff15\uff14\uff14\uff15\uff15")
    assert nt.text.endswith("50100234554455")


def test_find_span_tolerates_whitespace():
    text = "Account number:\n    50100234559821\nIFSC"
    assert find_span(text, "Account number: 50100234559821") is not None


def test_tg001_new_account_is_found_and_unknown(case_by_id, vendor):
    _, tokens = _tokens_for(case_by_id["TG-001"])
    accounts = unique_accounts(tokens)
    assert any(t.normalized.endswith("9821") for t in accounts)
    assert not any(vendor.is_known_account(t.normalized) for t in accounts)


def test_obfuscated_numbers_are_found_after_normalisation(case_by_id, vendor):
    for cid in ("TG-016", "TG-017"):
        _, tokens = _tokens_for(case_by_id[cid])
        accounts = unique_accounts(tokens)
        assert accounts, f"{cid}: no account token found"
        assert not vendor.is_known_account(accounts[0].normalized), cid


def test_phone_number_is_not_an_account(case_by_id):
    _, tokens = _tokens_for(case_by_id["TG-014"])
    assert not any(t.kind == "account" and t.normalized.startswith("91") for t in tokens)
    assert any(t.kind == "phone" for t in tokens)


def test_invoice_number_is_not_an_account(case_by_id):
    nt = normalize_text("Invoice INV-4471 for 120 days, please pay.")
    tokens = [t for t in find_tokens(nt) if t.kind == "account"]
    assert tokens == []


def test_known_account_is_flagged_as_known(case_by_id, vendor):
    _, tokens = _tokens_for(case_by_id["TG-008"])
    accounts = unique_accounts(tokens)
    assert accounts and all(vendor.is_known_account(t.normalized) for t in accounts)
