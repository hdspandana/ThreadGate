"""Boundaries on the demo UI.

This is a public, unauthenticated Streamlit app holding an API key and handing
pasted text to a paid model. The pipeline is the security boundary and does not
trust the UI, so nothing here is a control - but an unbounded input or a rendered
traceback is still a defect in something judges will click.

These are source-level assertions rather than imports, and that is deliberate:
a Streamlit script executes top to bottom on import, so `import streamlit_app`
runs a server. Asserting against the source is the only way to test these
properties without standing one up, and it still catches reintroduction.

What is NOT claimed here, and must not be added: authentication, distributed
rate limiting, or caching of pasted email. Session state is per browser session
and stores nothing but a timestamp.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "streamlit_app.py"
SRC = APP.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# the key is never displayed, in whole or in part
# ---------------------------------------------------------------------------
def test_no_part_of_the_key_is_ever_rendered():
    """It used to print the last four characters into the sidebar."""
    assert "[-4:]" not in SRC
    assert "ends ..." not in SRC


def test_key_status_returns_only_configured_or_not():
    m = re.search(r"def key_status.*?\n(?:.*?\n)*?    return .*?\n", SRC)
    assert m, "key_status not found"
    body = m.group(0)
    assert "configured" in body
    assert "k[-" not in body and "k[" not in body


def test_the_key_is_never_written_to_a_log_or_the_page():
    for pattern in (r"st\.write\(k", r"st\.write\(.*api_key", r"print\(.*api_key",
                    r"st\.markdown\(.*api_key", r"logging\..*api_key"):
        assert not re.search(pattern, SRC), pattern


# ---------------------------------------------------------------------------
# input is bounded
# ---------------------------------------------------------------------------
def test_there_is_a_maximum_pasted_email_length():
    m = re.search(r"^MAX_EMAIL_CHARS\s*=\s*(\d[\d_]*)", SRC, re.MULTILINE)
    assert m, "MAX_EMAIL_CHARS is not defined"
    assert int(m.group(1).replace("_", "")) > 0


def test_an_oversized_email_is_rejected_before_the_pipeline_sees_it():
    """Rejected with st.stop(), so no extractor call and no API spend."""
    assert len(re.findall(r"MAX_EMAIL_CHARS", SRC)) >= 2, (
        "the limit must be defined AND used"
    )
    guard = SRC.split("len(body) > MAX_EMAIL_CHARS", 1)[1]
    assert "st.stop()" in guard[:400], (
        "an oversized email must stop before the pipeline runs"
    )


# ---------------------------------------------------------------------------
# a failure shows a message, not a traceback
# ---------------------------------------------------------------------------
def test_tracebacks_are_never_rendered():
    # Call form, not the bare name: this file mentions st.exception in a comment
    # explaining why it is not used, and that mention is not a violation.
    assert not re.search(r"st\.exception\s*\(", SRC)


def test_the_raw_exception_message_is_not_put_on_the_page():
    """An exception string can carry back the email that was just pasted."""
    assert not re.search(r"st\.error\(f?[\"'].*\{exc\}", SRC)


def test_the_generic_failure_states_the_safe_outcome():
    """A failure must read as HOLD, because that is what the pipeline does."""
    # Split across source lines by the formatter, so match the part that is
    # contiguous rather than the sentence as a whole.
    assert "held for human" in SRC and "nothing has been cleared" in SRC


def test_the_diagnostics_panel_shows_only_the_exception_class():
    m = re.search(r"st\.code\(f?\"\{type\(exc\)\.__name__\}\"\)", SRC)
    assert m, "diagnostics should show the class name and nothing else"


# ---------------------------------------------------------------------------
# cooldown and timeout
# ---------------------------------------------------------------------------
def test_there_is_a_per_session_cooldown():
    assert "MIN_SECONDS_BETWEEN_RUNS" in SRC
    assert "st.session_state" in SRC


def test_the_cooldown_storage_holds_nothing_but_a_timestamp():
    """No caching of pasted email: only a float goes into session_state."""
    writes = re.findall(r"st\.session_state\.(\w+)\s*=", SRC)
    assert set(writes) == {"last_run_at"}, (
        f"session_state stores {sorted(set(writes))}; a pasted email must never "
        "be cached there"
    )


def test_a_timeout_is_handled_distinctly_from_other_failures():
    assert "except TimeoutError" in SRC
    assert "did not respond in time" in SRC


def test_the_extractor_enforces_a_request_timeout():
    """The UI message would be fiction without a real timeout underneath."""
    extract = (ROOT / "src" / "threadgate" / "extract.py").read_text(encoding="utf-8")
    assert "THREADGATE_HTTP_TIMEOUT_MS" in extract
    assert "HttpOptions" in extract


def test_a_model_timeout_is_both_an_extractor_error_and_a_timeout():
    import sys

    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))
    from threadgate.extract import ExtractorError, ModelTimeoutError

    e = ModelTimeoutError("x")
    # ExtractorError, so the pipeline's fail-closed path is unchanged...
    assert isinstance(e, ExtractorError)
    # ...and TimeoutError, so the UI can offer a retry instead of a dead end.
    assert isinstance(e, TimeoutError)


# ---------------------------------------------------------------------------
# what must NOT be added
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "forbidden",
    [
        "st.experimental_user",  # auth
        "st.login",  # auth
        "requests.exceptions",  # outbound call from the UI
        "@st.cache_data",  # would cache one visitor's email for the next
        "@st.cache_resource",
    ],
)
def test_no_authentication_and_no_caching_of_pasted_email(forbidden):
    assert forbidden not in SRC, forbidden


def test_xsrf_and_cors_defaults_are_left_alone():
    """Changing these would be a real security change made by accident."""
    config = (ROOT / ".streamlit" / "config.toml")
    if not config.exists():
        pytest.skip("no .streamlit/config.toml; defaults are in force")
    body = config.read_text(encoding="utf-8")
    for key in ("enableXsrfProtection", "enableCORS"):
        assert key not in body, f"{key} is set; the default is the safer choice"
