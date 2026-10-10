"""ThreadGate demo UI.

Deliberately thin: every decision shown here is produced by the pipeline, and
the UI has no logic of its own beyond rendering. That is the point - the gate
is the code, not the screen.
"""

from __future__ import annotations

import html
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from threadgate.baseline import rules_only  # noqa: E402
from threadgate.records import load_cases, load_vendors  # noqa: E402
from threadgate.clock import SystemClock  # noqa: E402
from threadgate.attestation import AttestationStore, VerificationEvent  # noqa: E402
from threadgate.pipeline import run_case  # noqa: E402
from threadgate.tokens import unique_accounts  # noqa: E402

sys.path.insert(0, str(ROOT / "eval"))
# The case-set labels, the system list and the disclaimers are imported from
# the evaluation harness rather than restated here, so the screen and the
# command line cannot drift apart.
from run_eval import (  # noqa: E402
    ALL_SYSTEMS,
    CATEGORIES,
    DISCLAIMER,
    EVAL_AS_OF,
    MODEL_SYSTEMS,
    SETS,
    by_category,
    gemini_available,
    metrics,
    run_system,
)
from threadgate.clock import fixed  # noqa: E402

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover
    pass

# Colours are chosen so that nothing reads as "approved". There is deliberately
# no green: CLEAR means "no change was identified by this prototype", which is
# not a statement that the email is safe, and it must not look like one.
# --- limits ---------------------------------------------------------------
# A pasted email is untrusted input handed to a paid API. These bound it. They
# are deliberately modest: this is a demo that runs on a shared community tier,
# and the goal is that one person clicking a button cannot burn the key or hang
# the app. This is NOT authentication, NOT a distributed rate limit and NOT a
# security boundary - a determined caller still talks to the API directly. The
# security boundary is the pipeline, which does not trust the UI at all.
MAX_EMAIL_CHARS = 20_000
MIN_SECONDS_BETWEEN_RUNS = 2.0
# An elapsed-time nag, not a network timeout. The real bounds live in
# the extractor: THREADGATE_HTTP_TIMEOUT_MS per attempt and
# THREADGATE_TOTAL_BUDGET_MS across the retry loop. Calling this a
# timeout would be a lie about where the limit is enforced.
SLOW_REQUEST_SECONDS = 45.0

BADGE = {
    "HOLD": ("#c1121f", "HOLD - verify out of band before anything executes"),
    "REVIEW": ("#8a5a00", "REVIEW - change matches the record; a human still attests"),
    "CLEAR": ("#37507a", "CLEAR - no change identified by this prototype"),
}

CSS = """
<style>
.emailbox {font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 13px;
  line-height: 1.55; background:#fbfbfc; border:1px solid #e3e6ea; border-radius:8px;
  padding:14px 16px; max-height:430px; overflow:auto; white-space:pre-wrap; word-break:break-word;}
mark {padding:1px 2px; border-radius:3px;}
mark.unknown {background:#ffd6d6; border-bottom:2px solid #c1121f;}
mark.known {background:#d8f3e0;}
mark.evidence {background:#fff3bf;}
mark.intent {background:#dbe7ff;}
.badge {color:#fff; padding:10px 16px; border-radius:8px; font-weight:700; font-size:19px;
  display:inline-block; letter-spacing:.2px;}
.small {font-size:12px; color:#5c6b7a;}
table.tg {width:100%; border-collapse:collapse; font-size:13px;}
table.tg th, table.tg td {border:1px solid #e3e6ea; padding:6px 8px; text-align:left;}
table.tg th {background:#f4f6f8;}

.destination-panel {
  background: #f8fafc;
  border: 1px solid #d6deea;
  border-left: 5px solid #37507a;
  border-radius: 12px;
  padding: 20px 22px;
  margin: 22px 0 30px 0;
  box-shadow: 0 2px 8px rgba(15, 31, 58, 0.04);
}

.destination-kicker {
  color: #526783;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 1.4px;
  margin-bottom: 7px;
}

.destination-heading {
  color: #14213d;
  font-size: 22px;
  font-weight: 750;
  line-height: 1.3;
  margin-bottom: 14px;
}

.destination-panel table.tg {
  background: white;
  border-collapse: separate;
  border-spacing: 0;
  border: 1px solid #d9e1eb;
  border-radius: 8px;
  overflow: hidden;
  font-size: 14px;
}

.destination-panel table.tg th {
  background: #e9eef5;
  color: #1b2c49;
  font-weight: 700;
  padding: 12px 14px;
  border-color: #d9e1eb;
}

.destination-panel table.tg td {
  padding: 13px 14px;
  border-color: #e1e7ef;
  vertical-align: middle;
}

.destination-panel table.tg tr:last-child td {
  border-bottom: none;
}

.destination-panel .small {
  color: #53647b;
}

@media (max-width: 768px) {
  .destination-panel {
    padding: 14px;
    margin: 16px 0 22px 0;
  }

  .destination-heading {
    font-size: 19px;
  }

  .destination-panel table.tg {
    font-size: 12px;
  }

  .destination-panel table.tg th,
  .destination-panel table.tg td {
    padding: 8px 7px;
    overflow-wrap: anywhere;
  }
}
</style>
"""


# ---------------------------------------------------------------------------
# secrets
# ---------------------------------------------------------------------------
def api_key() -> str | None:
    """Read the key from Streamlit secrets, then the environment. Never displayed."""
    try:
        k = st.secrets.get("GEMINI_API_KEY")  # type: ignore[union-attr]
        if k:
            return str(k)
    except Exception:  # noqa: BLE001 - st.secrets raises when no secrets file exists
        pass
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def key_status() -> tuple[bool, str]:
    """Present or absent. Nothing else.

    An earlier version printed the last four characters. Four characters of a
    secret is still part of the secret, it is rendered into a public demo, and
    it lands in any screenshot taken of the sidebar. Whether a key is present is
    the only thing the user needs to know.
    """
    return (True, "configured") if api_key() else (False, "not configured")


def export_key_to_environment() -> None:
    """Expose configured Streamlit secrets to the extractor process."""
    key = api_key()
    if key and not (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
    ):
        os.environ["GEMINI_API_KEY"] = key

    # Streamlit Cloud secrets are not automatically environment variables.
    try:
        configured_model = st.secrets.get("THREADGATE_MODEL")
    except Exception:
        configured_model = None

    # Preserve a model already configured in the local environment.
    if configured_model and not os.environ.get("THREADGATE_MODEL"):
        os.environ["THREADGATE_MODEL"] = str(configured_model)


# ---------------------------------------------------------------------------
# rendering
# ---------------------------------------------------------------------------
def highlight(text: str, spans: list[tuple[int, int, str]]) -> str:
    cls: list[str | None] = [None] * len(text)
    for start, end, kind in spans:
        for i in range(max(0, start), min(len(text), end)):
            if cls[i] is None:
                cls[i] = kind
    out: list[str] = []
    i = 0
    while i < len(text):
        j = i
        while j + 1 < len(text) and cls[j + 1] == cls[i]:
            j += 1
        seg = html.escape(text[i: j + 1])
        out.append(f'<mark class="{cls[i]}">{seg}</mark>' if cls[i] else seg)
        i = j + 1
    return "".join(out).replace("\n", "<br>")


def spans_for(result) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    vendor = VENDORS[result.vendor_id]
    for tok in unique_accounts(result.tokens):
        kind = "known" if vendor.is_known_account(tok.normalized) else "unknown"
        spans.append(result.nt.to_raw_span(tok.start, tok.end) + (kind,))
    if result.validation and result.validation.intent_span_norm:
        spans.append(result.nt.to_raw_span(*result.validation.intent_span_norm) + ("intent",))
    if result.validation:
        for c in result.validation.verified_claims:
            if c.evidence_span_norm:
                spans.append(result.nt.to_raw_span(*c.evidence_span_norm) + ("evidence",))
    return spans


def diff_table(result) -> str:
    rows = ["<table class='tg'><tr><th>Field</th><th>On file</th><th>Requested</th><th>Risk</th></tr>"]
    for d in result.decision.diffs:
        if not d.changed and not d.pre_registered:
            continue
        old = html.escape(str(d.old_value or "-"))
        new = html.escape(str(d.new_value or "-"))
        tag = "pre-registered" if d.pre_registered else d.risk
        rows.append(f"<tr><td>{d.field}</td><td>{old}</td><td><b>{new}</b></td><td>{tag}</td></tr>")
    if len(rows) == 1:
        return "<p class='small'>No field-level difference was verified against the record.</p>"
    rows.append("</table>")
    return "".join(rows)


# Reference and attestation states. No green anywhere: a muted blue is the
# "nothing to see" colour, amber and red are the two that need a person.
STATE_COLOUR = {"CURRENT": "#37507a", "STALE": "#8a5a00", "MISSING": "#c1121f"}
STATE_NOTE = {
    "CURRENT": "The record on file was confirmed inside its freshness window, so "
               "it is treated as usable evidence of the destination.",
    "STALE": "The record has not been reconfirmed recently enough to trust. "
             "Nothing here can clear on the strength of it.",
    "MISSING": "There is no payment destination on file at all, so there is "
               "nothing to verify the request against.",
}
ATTEST_COLOUR = {
    "NOT_REQUIRED": "#37507a", "PENDING": "#8a5a00",
    "SATISFIED": "#37507a", "REJECTED": "#c1121f",
}
# The pipeline emits machine reason codes. They are the right thing to log and
# the wrong thing to show a judge, so each one is rendered as a sentence and the
# raw codes go in a collapsed panel. This is presentation only - nothing here is
# read back into a decision, and the mapping is not a policy input.
REASON_TEXT = {
    "unknown_account_token":
        "An account-like number in this email is not the account on file and not a "
        "pre-registered alternate.",
    "pre_registered_alternate_routing":
        "This names a pre-registered alternate that is not the currently active "
        "destination, and asks for payments to be routed to it. That is at least a "
        "REVIEW no matter how the message reads.",
    "unverifiable_no_values":
        "The email talks about a payment change but no value in it could be checked "
        "against the record.",
    "destination_out_of_band":
        "The destination lives somewhere this pipeline cannot read - an image, a PDF "
        "or a portal. Nothing is opened; a human retrieves it out of band.",
    "no_change_evidenced":
        "The model reported no change, and the sentence it quoted actually says so.",
    "nothing_to_gate":
        "No change was identified, so there is nothing for the gate to decide.",
    "reference_stale_record":
        "The record on file is past its confirmation window, so it floors at REVIEW "
        "rather than CLEAR.",
    "reference_missing_record":
        "There is no payment destination on file to check against.",
    "reference_missing_destination_change":
        "There is no payment destination on file, and this email asks to change the "
        "destination.",
    "attestation_rejected":
        "A verification event was presented and refused. The decision is unchanged.",
    "extractor_failed_fail_closed":
        "The interpreter failed. The gate fails closed rather than guessing.",
    "I1_UNKNOWN_ACCOUNT_TOKEN":
        "An account-like number in this email is not on file and not a pre-registered "
        "alternate.",
}


def explain(reason: str) -> str:
    """One reason code as a sentence. Unknown codes pass through unchanged.

    Passing through is deliberate: a code with no translation still appears, so
    a new one shows up on screen as itself rather than vanishing behind a
    default message that claims to explain it.
    """
    if reason in REASON_TEXT:
        return REASON_TEXT[reason]
    head = reason.split(":", 1)[0]
    fields = reason.split(":", 1)[1] if ":" in reason else ""
    if head == "high_risk_field_change":
        return f"High-risk field(s) differ from the record: {fields}."
    if head == "medium_risk_field_change":
        return f"Medium-risk field(s) differ from the record: {fields}."
    if head == "verified_low_risk_change":
        return f"A low-risk field changes: {fields}. A human still attests."
    return reason


ATTEST_NOTE = {
    "NOT_REQUIRED": "No change was identified, so there is nothing to verify.",
    "PENDING": "A human must verify this out of band and attest before it executes. "
               "The attestation is single-use and bound to this request, this "
               "destination and this record version.",
    "SATISFIED": "A verification event bound to this exact request, destination and "
                 "record version has been accepted once.",
    "REJECTED": "An attestation was presented and refused - wrong request, wrong "
                "destination, wrong record version, or already used. The decision "
                "is unchanged.",
}


def render(result, baseline_decision: str) -> None:
    colour, label = BADGE[result.decision.decision]
    st.markdown(f"<span class='badge' style='background:{colour}'>{label}</span>", unsafe_allow_html=True)
    st.caption(
        f"extractor `{result.extractor}` - {result.elapsed_ms:.0f} ms - "
        f"rules-only baseline says **{baseline_decision}**"
    )

    st.markdown(
        "<section class='destination-panel'>"
        "<div class='destination-kicker'>DESTINATION CHECK</div>"
        "<div class='destination-heading'>"
        "Requested destination vs. trusted record"
        "</div>"
        f"{diff_table(result)}"
        "</section>",
        unsafe_allow_html=True,
    )

    left, right = st.columns([3, 2])
    with left:
        st.subheader("The email")
        st.markdown(
            f"<div class='emailbox'>{highlight(result.nt.raw, spans_for(result))}</div>",
            unsafe_allow_html=True,
        )
        st.markdown(
            "<span class='small'>"
            "<mark class='unknown'>account number not on file</mark> "
            "<mark class='known'>account on file</mark> "
            "<mark class='intent'>sentence the model quoted for its intent</mark> "
            "<mark class='evidence'>evidence for a verified claim</mark>"
            "</span>",
            unsafe_allow_html=True,
        )
        if result.nt.normalizations_applied:
            st.caption("normalisation applied: " + ", ".join(result.nt.normalizations_applied))

    with right:
        st.subheader("Why")
        for r in result.decision.reasons:
            st.markdown(f"- {explain(r)}")
        with st.expander("Reason codes"):
            for r in result.decision.reasons:
                st.code(r)

        st.markdown("#### The record this was checked against")
        st.markdown(
            f"<span class='badge' style='background:{STATE_COLOUR.get(result.decision.reference_state, '#4a4a4a')}'>"
            f"{result.decision.reference_state}</span> "
            f"<span class='small'>reference <code>{result.decision.reference_version}</code></span>",
            unsafe_allow_html=True,
        )
        st.caption(STATE_NOTE.get(result.decision.reference_state, ""))

        st.markdown("#### Human verification")
        status = result.decision.attestation_status
        st.markdown(
            f"<span class='badge' style='background:{ATTEST_COLOUR.get(status, '#4a4a4a')}'>"
            f"{status}</span>",
            unsafe_allow_html=True,
        )
        st.caption(ATTEST_NOTE.get(status, ""))
        if result.verification is not None:
            st.caption(
                "An attestation would have to be bound to this request, this "
                "destination digest and this reference version: "
                f"`{result.verification.destination_digest[:16]}…`"
            )


        if result.decision.findings:
            st.markdown("#### Findings")
            for f in result.decision.findings:
                guard = " (does not consult the model)" if f.independent_of_model else ""
                st.markdown(f"- **{f.code}**{guard}: {f.message}")

        if result.decision.checklist:
            st.markdown("#### Before anything executes")
            for i, item in enumerate(result.decision.checklist, 1):
                st.markdown(f"{i}. {item}")

    with st.expander("What the model returned, and what the validator admitted"):
        st.markdown("**Model output (untrusted):**")
        st.json(result.extraction.model_dump(), expanded=False)
        st.markdown("**Validator verdict:**")
        st.json(
            {
                "intent_evidenced": result.validation.intent_evidenced,
                "verified_claims": [c.claim.model_dump() for c in result.validation.verified_claims],
                "dropped_claims": result.dropped_claims if hasattr(result, "dropped_claims") else result.validation.dropped_claims,
                "violations": result.validation.violations,
            },
            expanded=False,
        )
        if result.notes:
            st.caption("; ".join(result.notes))


# What each harness row means. Kept next to the table that displays them so a
# reviewer cannot read an ablation as an opponent.
SYSTEM_LABELS = {
    "rules_raw": "rules on raw text - no model, no normalisation",
    "rules_norm": "rules on normalised text - no model",
    "ai_only": "the model decides - evaluation baseline only, never a code path in the gate",
    "gemini": "ThreadGate - the model interprets, code decides",
    "compromised": "ThreadGate, with the model steered to always report no change",
    "compromised_q": "ThreadGate, with the model fabricating a verbatim quote for a claim "
    "that is not in the email",
    "hybrid_no_scan": "ThreadGate, ablation - independent destination scan removed",
    "hybrid_no_validation": "ThreadGate, ablation - evidence validation removed",
    "offline": "deterministic test double - not a model, and never quoted as a result",
}


# ---------------------------------------------------------------------------
# page
# ---------------------------------------------------------------------------
st.set_page_config(page_title="ThreadGate", page_icon="\U0001f6aa", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

VENDORS = load_vendors(ROOT / "data" / "records" / "vendor_master.json")
export_key_to_environment()

st.title("ThreadGate")
st.markdown(
    "**AI interprets. Deterministic code verifies. A human attests before execution.**"
)
st.caption(
    "Payment-change requests are checked against the trusted vendor record—not "
    "judged by how convincing the email sounds."
)

configured, status = key_status()
case_set_key = st.sidebar.radio(
    "Case set", list(SETS), index=0, format_func=lambda k: SETS[k]["title"]
)
st.sidebar.caption(SETS[case_set_key]["caveat"])
CASES = load_cases(SETS[case_set_key]["path"])
# Pinned for benchmark runs; deliberately NOT used for the single-email path.
EVAL_CLOCK = fixed(EVAL_AS_OF)
mode = st.sidebar.selectbox(
    "Extractor",
    ["gemini", "offline", "compromised", "compromised_quote"],
    index=0 if configured else 1,
    help="`compromised` and `compromised_quote` are adversarial harnesses: the model is steered "
    "to always report no change. The gate should still hold the high-risk cases.",
)
st.sidebar.caption(f"API key: {status}")
if mode == "gemini" and not configured:
    st.sidebar.warning(
        "No key found. Add GEMINI_API_KEY to .env locally, or to the deployment secret store. "
        "Falling back would be misleading, so pick `offline` to explore the pipeline."
    )

source = st.sidebar.radio("Input", ["Frozen case", "Paste an email"], index=0)

case = None
if source == "Frozen case":
    labels = {
        c["id"]: f"{c['id']} - {c['title']}  [{c['expected_decision']}]" for c in CASES
    }
    chosen = st.sidebar.selectbox("Case", list(labels), format_func=lambda k: labels[k])
    case = next(c for c in CASES if c["id"] == chosen)
    st.sidebar.caption(f"_{case['tests']}_")
else:
    vendor_id = st.sidebar.selectbox("Vendor on file", list(VENDORS))
    body = st.text_area(
        "Email text",
        height=260,
        placeholder="From: ...\nSubject: ...\n\nPaste the email here.",
    )
    if body.strip():
        if len(body) > MAX_EMAIL_CHARS:
            # Rejected before the pipeline sees it, and before any API call.
            st.error(
                f"This email is {len(body):,} characters. The demo accepts up to "
                f"{MAX_EMAIL_CHARS:,}. Nothing has been sent anywhere."
            )
            st.stop()
        first_line = body.strip().splitlines()[0]
        case = {
            "id": "ad-hoc",
            "vendor_id": vendor_id,
            "email": {
                "from": first_line.replace("From:", "").strip() if first_line.lower().startswith("from:") else "",
                "reply_to": "",
                "subject": "",
                "body": body,
                "auth": {},
            },
        }

if case is None:
    st.info("Choose a frozen case on the left, or paste an email.")
    st.stop()

# A per-session cooldown on model-backed runs. Held in session_state, so it is
# per browser session and costs nothing to a second visitor - which is the right
# trade for a demo, and is why this is not described as rate limiting.
if "last_run_at" not in st.session_state:
    st.session_state.last_run_at = 0.0
# Only the model-backed extractors are throttled. `offline` is a deterministic
# test double running locally, so slowing it would cost interactivity for
# nothing.
_now = time.monotonic()
_since = _now - st.session_state.last_run_at
if mode in MODEL_SYSTEMS and configured and _since < MIN_SECONDS_BETWEEN_RUNS:
    st.info(
        f"One request every {MIN_SECONDS_BETWEEN_RUNS:.0f}s in the demo. "
        f"Retrying in {MIN_SECONDS_BETWEEN_RUNS - _since:.1f}s - press Rerun, "
        "or just wait a moment and interact again."
    )
    st.stop()

# The single-use store lives in the session, so the replay demo has somewhere to
# remember that an event was already spent. It holds event ids and bindings only
# - never the email, never the record.
if "attest_store" not in st.session_state:
    st.session_state.attest_store = AttestationStore()
if "minted_event" not in st.session_state:
    st.session_state.minted_event = None
if "pending_presentation" not in st.session_state:
    st.session_state.pending_presentation = None

# Consumed once, then cleared, so a presentation is applied to exactly one run.
presented = st.session_state.pending_presentation
st.session_state.pending_presentation = None

try:
    # The wall clock, because a deployed demo should judge the record
    # against real time. The evaluation pins the date instead so its
    # numbers are reproducible.
    result = run_case(
        case, VENDORS, extractor_mode=mode, clock=SystemClock(),
        store=st.session_state.attest_store, presented_event=presented,
    )
    st.session_state.last_run_at = time.monotonic()
except TimeoutError:
    st.session_state.last_run_at = time.monotonic()
    st.error(
        "The model did not respond in time. Nothing has been decided: treat this "
        "request as HOLD and verify out of band. Press Rerun to try again."
    )
    st.stop()
except Exception as exc:  # noqa: BLE001
    st.session_state.last_run_at = time.monotonic()
    # Deliberately not `st.exception` and not the raw message. A traceback in a
    # public demo leaks module layout, and an exception string can carry back the
    # email text that was just pasted. The safe outcome is stated instead; the
    # class name is enough for someone debugging, and it goes in a collapsed
    # panel rather than on the page.
    st.error(
        "The gate could not process this request. It has been held for human "
        "review - nothing has been cleared."
    )
    with st.expander("Diagnostics"):
        st.code(f"{type(exc).__name__}")
    st.stop()

if result.elapsed_ms and result.elapsed_ms > SLOW_REQUEST_SECONDS * 1000:
    # Deliberately an elapsed-time notice, not a timeout warning: nothing was
    # cut short and nothing failed. The decision this page is showing is
    # complete - it was merely slow to arrive.
    st.warning(
        f"This request took {result.elapsed_ms / 1000:.1f}s end to end, which is "
        f"longer than the {SLOW_REQUEST_SECONDS:.0f}s this page treats as "
        f"sluggish. Nothing timed out and nothing was cut short: the decision "
        f"shown below is complete. The gate is synchronous by design, so a slow "
        f"model shows up as latency, not as a weaker decision."
    )

baseline = rules_only(case, VENDORS[case["vendor_id"]]).decision
render(result, baseline)

# --- the single-use binding, demonstrated -------------------------------
# Nothing here is a signature. The point being shown is narrower and true: a
# verification is bound to one request, one destination and one record version,
# and presenting it a second time is refused even though nothing about it has
# changed. That is a property of the binding, not of cryptography.
with st.expander("Demonstrate the single-use verification binding"):
    st.caption(
        "This is **not** a cryptographic signature and proves nothing about who "
        "attested. It shows one thing: an attestation is bound to this request, this "
        "destination digest and this reference version, and it can be spent once."
    )
    ctx = result.verification
    if ctx is None:
        st.info("No verification context for this case.")
    else:
        st.code(
            f"request      {ctx.request_id}\n"
            f"destination  {ctx.destination_digest[:24]}...\n"
            f"reference    {ctx.reference_version}\n"
            f"vendor       {ctx.vendor_id}",
            language="text",
        )
        mint, replay = st.columns(2)
        with mint:
            if st.button("Mint and present a verification event", type="secondary"):
                event = VerificationEvent(
                    event_id=f"EVT-{ctx.request_id[:12]}",
                    vendor_id=ctx.vendor_id,
                    request_id=ctx.request_id,
                    destination_digest=ctx.destination_digest,
                    reference_version=ctx.reference_version,
                    attested_by="demo",
                    attested_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                )
                st.session_state.minted_event = event
                st.session_state.pending_presentation = event
                st.rerun()
        with replay:
            already = st.session_state.minted_event is not None
            if st.button(
                "Present the same event again",
                type="secondary",
                disabled=not already,
                help="Mint an event first." if not already else
                     "Same event id, same binding - and it must be refused.",
            ):
                st.session_state.pending_presentation = st.session_state.minted_event
                st.rerun()

        if result.decision.attestation_status in ("SATISFIED", "REJECTED"):
            st.markdown(
                f"**Outcome:** `{result.decision.attestation_status}` "
                f"/ `{result.decision.attestation_code}`"
            )
            st.caption(ATTEST_NOTE.get(result.decision.attestation_status, ""))
            if result.decision.attestation_code == "ATTESTATION_REPLAY":
                st.success(
                    "The same event, presented unchanged against the same request, "
                    "was refused. That is the binding working - not a signature, "
                    "and not proof of who attested."
                )
        if st.session_state.minted_event and st.button("Clear the demo store"):
            st.session_state.attest_store = AttestationStore()
            st.session_state.minted_event = None
            st.rerun()

st.divider()
st.subheader("The whole corpus, not one email")
st.caption(
    f"Benchmark runs use the pinned evaluation date **{EVAL_AS_OF}**, the same "
    f"date `python eval/run_eval.py` uses, so this table reproduces the "
    f"command-line numbers. Single-email runs above use the real clock: a "
    f"deployed demo should judge the record against actual time."
)
st.caption(
    "Two different ways to be too permissive, and both are shown. `unsafe` is a case that "
    "should have been held but was not - the only error that can lose money. `non-CLR` is any "
    "case the gate should have stopped that came back CLEAR. A system can read safety 100% and "
    "still wave a gated case through, which is why `no-bypass %` sits next to `safety %` and "
    "neither may be quoted alone. `false hold` is a case a human was asked to review "
    "unnecessarily - it costs time, not money."
)
with st.expander("What each system is"):
    for name in ALL_SYSTEMS:
        st.markdown(f"- `{name}` - {SYSTEM_LABELS[name]}")

if st.button(f"Run {len(CASES)} cases across every system", type="secondary"):
    have_key = gemini_available()
    systems = [s for s in ALL_SYSTEMS if s != "offline"]
    skipped = [s for s in systems if s in MODEL_SYSTEMS and not have_key]
    systems = [s for s in systems if s not in skipped]

    rows = []
    results_by_system: dict[str, list] = {}
    metrics_by_system: dict[str, dict] = {}
    progress = st.progress(0.0)
    for i, sysname in enumerate(systems):
        with st.spinner(f"running {sysname}..."):
            # The same pinned clock the CLI uses. Without it the benchmark
            # judged reference freshness against the wall clock, so its
            # numbers drifted away from `python eval/run_eval.py` as real
            # time passed and neither surface could reproduce the other.
            res = run_system(sysname, CASES, VENDORS, clock=EVAL_CLOCK)
            m = metrics(res)
            results_by_system[sysname] = res
            metrics_by_system[sysname] = m
            if m.get("invalid"):
                # An errored run measures nothing. The pipeline fails closed,
                # so its HOLDs are not predictions and must not be shown as a
                # safety score: every figure on the row is blanked and the
                # error count is the only number left.
                rows.append(
                    {
                        "system": sysname,
                        "accuracy %": "INVALID",
                        "unsafe": "-",
                        "non-CLR": "-",
                        "safety %": "-",
                        "no-bypass %": "-",
                        "false holds": f'{m["extractor_errors"]} errors',
                    }
                )
            else:
                rows.append(
                    {
                        "system": sysname,
                        "accuracy %": m["accuracy"],
                        "unsafe": m["unsafe_missed_holds"],
                        "non-CLR": m["non_clear_releases"],
                        "safety %": m["safety_pct"],
                        "no-bypass %": m["no_bypass_pct"],
                        "false holds": m["false_holds"],
                    }
                )
        progress.progress((i + 1) / len(systems))

    st.table(rows)

    for s, m in zip(systems, rows):
        if metrics_by_system[s].get("invalid"):
            ids = ", ".join(metrics_by_system[s].get("error_case_ids", [])[:5])
            st.error(
                f"`{s}` is INVALID: {metrics_by_system[s]['extractor_errors']} case(s) "
                f"failed in the model layer (e.g. {ids}). No figure from this row may "
                f"be quoted - the pipeline fails closed, so its HOLDs are not "
                f"predictions."
            )
            continue
        if m["unsafe"]:
            ids = ", ".join(metrics_by_system[s]["missed_hold_ids"])
            st.error(f"`{s}` released {m['unsafe']} case(s) that should have been held: {ids}")
        if m["non-CLR"]:
            ids = ", ".join(metrics_by_system[s]["non_clear_release_ids"])
            st.error(
                f"`{s}` returned CLEAR on {m['non-CLR']} case(s) the gate was supposed to "
                f"stop: {ids}"
            )

    if skipped:
        st.warning(
            "Skipped without an API key: " + ", ".join(f"`{s}`" for s in skipped) + ". "
            "Add `GEMINI_API_KEY` to the deployment secret store and re-run to fill in the "
            "model rows. No number is shown for a system that did not run."
        )

    assignments = json.loads(CATEGORIES.read_text(encoding="utf-8"))["assignments"]
    per_cat = {s: by_category(r, assignments) for s, r in results_by_system.items()}
    cat_rows = []
    for cat in sorted({c for s in systems for c in per_cat[s]}):
        row = {"category": cat, "n": per_cat[systems[0]][cat]["n"]}
        for s in systems:
            m = per_cat[s].get(cat)
            if not m:
                row[s] = "-"
            elif m.get("invalid"):
                row[s] = "INVALID"
            else:
                row[s] = (
                    f"{m['accuracy']:.0f} (u{m['unsafe_missed_holds']} "
                    f"n{m['non_clear_releases']})"
                )
        cat_rows.append(row)
    st.markdown("**Per-category accuracy** - `u` is unsafe: a hold that was released. `n` counts non-CLEAR releases: cases the gate should have stopped that came back CLEAR.")
    st.table(cat_rows)
    st.caption(
        "Categories were assigned after both case sets were frozen, so they describe where each "
        "system helps or fails; they do not change any expected decision. The point of this table "
        "is the spread: the model earns its place on negation, mention-versus-request and "
        "token-less requests, and it contributes nothing on obfuscation, where the deterministic "
        "scanner carries the case."
    )
    with st.expander("Read this before quoting any number"):
        st.code(DISCLAIMER)
