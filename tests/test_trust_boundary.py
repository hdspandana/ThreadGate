"""The production model path must never see the trusted record.

The architecture says the AI is an untrusted semantic interpreter and the
comparator is the only component that obtains trusted current values. That is
only true if the model is not shown the record in the first place: a model that
can see the account on file can tailor its reading to match it, and a prompt
leak would disclose the trusted reference.

So `build_production_prompt` takes no vendor at all, and these tests prove it
with a vendor whose every trusted field carries a unique marker that must not
appear anywhere in the production prompt.

The ai_only baseline is the deliberate exception - it is the "model decides"
comparison, it is evaluation-only, and it is asserted here to be the only
record-aware builder.
"""

from __future__ import annotations

import copy
import dataclasses
import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from threadgate.extract import (  # noqa: E402
    PRODUCTION_SYSTEM_PROMPT,
    build_ai_only_prompt,
    build_production_prompt,
    gemini_extract,
)
from threadgate.normalize import normalize_text  # noqa: E402
from threadgate.records import load_vendors  # noqa: E402
from threadgate.schema import Claim  # noqa: E402

VENDORS = load_vendors(ROOT / "data" / "records" / "vendor_master.json")

# A marker that cannot occur in any legitimate prompt. If any of this reaches
# the production prompt, the trust boundary is broken.
SECRET = "ZQ7XTRUSTBOUNDARY9K"

SECRET_VENDOR_FIELDS = (
    "account_number",
    "ifsc",
    "swift",
    "bank_name",
    "branch",
    "beneficiary_name",
    "currency",
    "payment_terms",
    "remittance_email",
    "contact_person",
    "contact_phone",
)


def secret_vendor():
    """A vendor whose every trusted field carries the marker."""
    base = VENDORS["V-1001"]
    data = copy.deepcopy(base.data)
    data["vendor_id"] = f"V-{SECRET}"
    data["display_name"] = f"Marker Corp {SECRET}"
    data["legal_name"] = f"Marker Corp {SECRET} Ltd"
    data["verified_domains"] = [f"{SECRET}.example"]
    for key in ("bank", "payment_defaults", "verified_contacts"):
        node = data.get(key)
        if isinstance(node, dict):
            for field in node:
                node[field] = f"{SECRET}-{field}"
    data["allowlisted_accounts"] = [
        {**a, "account_number": f"{SECRET}-alt"} for a in data.get("allowlisted_accounts", [])
    ]
    out = dataclasses.replace(base, data=data)
    out.__post_init__()
    return out


EMAIL = (
    "From: ar@northwind.example\n"
    "Subject: Remittance details\n\n"
    "Hi,\n\nPlease update our account to 50100234559821, IFSC HDFC0008890.\n\nThanks\n"
)


# ---------------------------------------------------------------------------
# the production builder
# ---------------------------------------------------------------------------
def test_the_production_prompt_builder_takes_no_vendor():
    """Signature-level: there is nowhere to pass the record."""
    params = list(inspect.signature(build_production_prompt).parameters)
    assert params == ["nt"], params


def test_the_production_extractor_takes_no_vendor():
    """`gemini_extract` must not accept a Vendor/trusted reference object."""
    params = inspect.signature(gemini_extract).parameters
    assert "vendor" not in params, params
    assert list(params)[0] == "nt"
    assert getattr(gemini_extract, "email_only", False) is True, (
        "the production extractor must be marked email_only so the pipeline "
        "calls it with the email alone"
    )


def test_no_trusted_record_field_reaches_the_production_prompt():
    """The marker test. Every trusted field is marked; none may appear."""
    vendor = secret_vendor()
    for field in SECRET_VENDOR_FIELDS:
        assert SECRET in str(vendor.current(field) or ""), (
            f"{field} was not marked, so the test would be vacuous")
    nt = normalize_text(EMAIL)
    prompt = build_production_prompt(nt)
    assert SECRET not in prompt
    assert "VENDOR ON FILE" not in prompt
    assert "CURRENT RECORD" not in prompt
    assert "VERIFIED DOMAINS" not in prompt


def test_the_production_prompt_contains_the_email_and_nothing_else_structural():
    nt = normalize_text(EMAIL)
    prompt = build_production_prompt(nt)
    assert "50100234559821" in prompt, "the email itself must be present"
    assert prompt.count("----- BEGIN EMAIL") == 1
    assert prompt.count("----- END EMAIL") == 1


def test_the_production_system_prompt_claims_no_record_access():
    """Forbidden phrases are ones that describe what the model HAS.

    "value on file" is deliberately absent from that list: the prompt must say
    that `old_value` is NOT the value on file, and a test that bans the phrase
    outright would prevent the very sentence that makes the rule explicit.
    """
    low = PRODUCTION_SYSTEM_PROMPT.lower()
    for phrase in ("vendor on file", "current record", "verified domains",
                   "the record on file", "record summary", "taken from the record"):
        assert phrase not in low, phrase
    assert "you have not been given" in low, "the model must be told it cannot see the record"


def test_the_production_system_prompt_defines_old_value_as_email_stated():
    """`old_value` may not be described as 'the value on file'."""
    low = PRODUCTION_SYSTEM_PROMPT.lower()
    assert "old_value" in low
    assert "not the value on file" in low or "is not the value on file" in low


def test_the_claim_schema_does_not_describe_old_value_as_the_record():
    desc = (Claim.model_fields["old_value"].description or "").lower()
    assert "on file" not in desc or "not" in desc, desc
    assert "email" in desc, desc


# ---------------------------------------------------------------------------
# end-to-end: what actually goes to the API
# ---------------------------------------------------------------------------
def test_the_prompt_sent_to_the_api_carries_no_record(monkeypatch):
    """Drive the real gemini_extract with a fake client and inspect the request.

    This is the test that matters: it checks the string handed to the SDK, not
    just the builder in isolation.
    """
    import threadgate.extract as extract_mod

    # A fake key: this test is about what goes in the request, not about auth.
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    captured: dict = {}

    class _Resp:
        text = ('{"intent": "change_request", "intent_evidence": "x", '
                '"summary": "s", "claims": []}')

    class _Models:
        def generate_content(self, model, contents, config):
            captured["contents"] = contents
            captured["system"] = getattr(config, "system_instruction", None)
            captured["schema"] = getattr(config, "response_schema", None)
            return _Resp()

    class _Client:
        def __init__(self, api_key=None, **kw):
            captured["api_key"] = api_key
            self.models = _Models()

    class _Types:
        # staticmethod: as a plain class attribute this would be bound as a
        # method and receive `self` as a phantom first positional argument.
        GenerateContentConfig = staticmethod(lambda **kw: type("C", (), kw))

    import types as pytypes
    fake_genai = pytypes.ModuleType("google.genai")
    fake_genai.Client = _Client
    fake_genai.types = _Types()
    fake_google = pytypes.ModuleType("google")
    fake_google.genai = fake_genai
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    monkeypatch.setattr(extract_mod, "time.sleep", lambda s: None, raising=False)

    vendor = secret_vendor()
    nt = normalize_text(EMAIL)
    # The keyword form is asserted, not the positional one, and that precision
    # is the whole test. `gemini_extract(nt, model=None)` takes a second
    # positional parameter, so a sloppy `gemini_extract(nt, vendor)` binds the
    # record to the model *name* - silently accepted, and harmless only because
    # the record never reaches the prompt either way. `vendor=` is what must be
    # impossible, and it is.
    with pytest.raises(TypeError):
        gemini_extract(nt, vendor=vendor)
    gemini_extract(nt)

    assert SECRET not in captured["contents"]
    assert SECRET not in str(captured["system"])
    assert captured["system"] == PRODUCTION_SYSTEM_PROMPT
    assert "50100234559821" in captured["contents"]


# ---------------------------------------------------------------------------
# the ai_only baseline is the deliberate, isolated exception
# ---------------------------------------------------------------------------
def test_the_ai_only_baseline_does_receive_the_record():
    """It is the comparison. Being record-aware is the whole point of it."""
    vendor = secret_vendor()
    nt = normalize_text(EMAIL)
    prompt = build_ai_only_prompt(nt, vendor)
    assert SECRET in prompt, "the baseline must see the record to be a fair comparison"


def test_the_two_prompt_builders_are_not_the_same_function():
    assert build_production_prompt is not build_ai_only_prompt
    params = list(inspect.signature(build_ai_only_prompt).parameters)
    assert params == ["nt", "vendor"], params


def test_the_ai_only_prompt_is_not_used_by_the_production_path():
    src = Path(__file__).resolve().parents[1] / "src" / "threadgate" / "extract.py"
    text = src.read_text(encoding="utf-8")
    body = text.split("def gemini_extract", 1)[1].split("\ndef ", 1)[0]
    assert "build_ai_only_prompt" not in body
    assert "build_production_prompt" in body
