"""ThreadGate demo UI.

Deliberately thin: every decision shown here is produced by the pipeline, and
the UI has no logic of its own beyond rendering. That is the point - the gate
is the code, not the screen.
"""

from __future__ import annotations

import html
import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from threadgate.baseline import rules_only  # noqa: E402
from threadgate.records import load_cases, load_vendors  # noqa: E402
from threadgate.pipeline import run_case  # noqa: E402
from threadgate.tokens import unique_accounts  # noqa: E402

sys.path.insert(0, str(ROOT / "eval"))
from run_eval import metrics, run_system  # noqa: E402

CASE_SETS = {
    "frozen_v2 (40 cases)": ROOT / "data" / "cases" / "frozen_v2.json",
    "frozen_v1 (20 cases)": ROOT / "data" / "cases" / "frozen_v1.json",
}

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # pragma: no cover
    pass

BADGE = {
    "HOLD": ("#c1121f", "HOLD - needs a human"),
    "ALLOW": ("#1b7f4f", "ALLOW - verified change"),
    "NO_CHANGE": ("#37507a", "NO CHANGE - nothing to gate"),
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
    k = api_key()
    if not k:
        return False, "not configured"
    return True, f"configured (ends ...{k[-4:]})"


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


def render(result, baseline_decision: str) -> None:
    colour, label = BADGE[result.decision.decision]
    st.markdown(f"<span class='badge' style='background:{colour}'>{label}</span>", unsafe_allow_html=True)
    st.caption(
        f"extractor `{result.extractor}` - {result.elapsed_ms:.0f} ms - "
        f"rules-only baseline says **{baseline_decision}**"
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
            st.markdown(f"- `{r}`")
        st.markdown("#### Diff against the record")
        st.markdown(diff_table(result), unsafe_allow_html=True)

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


# ---------------------------------------------------------------------------
# page
# ---------------------------------------------------------------------------
st.set_page_config(page_title="ThreadGate", page_icon="\U0001f6aa", layout="wide")
st.markdown(CSS, unsafe_allow_html=True)

VENDORS = load_vendors(ROOT / "data" / "records" / "vendor_master.json")

st.title("ThreadGate")
st.markdown(
    "**AI interprets the email. Code verifies the change against the record. "
    "A human attests before anything executes.**"
)
st.markdown(
    "AI-written payment-change mail is fluent, so judging the *wording* gets weaker every year. "
    "Judging the *requested change against the record* does not depend on how good the writing is. "
    "ThreadGate gates the action, not the prose."
)

configured, status = key_status()
case_set_name = st.sidebar.radio("Case set", list(CASE_SETS), index=0)
CASES = load_cases(CASE_SETS[case_set_name])
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

try:
    result = run_case(case, VENDORS, extractor_mode=mode)
except Exception as exc:  # noqa: BLE001
    st.error(f"Pipeline failed: {exc}")
    st.stop()

baseline = rules_only(case, VENDORS[case["vendor_id"]]).decision
render(result, baseline)

st.divider()
st.subheader("The whole corpus, not one email")
st.caption(
    "`unsafe` counts cases that should be held but were not - the only error that can lose money. "
    "`false hold` counts cases a human was asked to review unnecessarily - it costs time, not money."
)
if st.button(f"Run all {len(CASES)} cases with `{mode}`", type="secondary"):
    systems = ["rules_raw", "rules_norm"] + ([mode] if mode != "gemini" else []) + ["compromised", "compromised_q"]
    if mode == "gemini":
        systems = ["rules_raw", "rules_norm", "gemini", "compromised", "compromised_q"]
    rows = []
    progress = st.progress(0.0)
    for i, sysname in enumerate(dict.fromkeys(systems)):
        with st.spinner(f"running {sysname}..."):
            res = run_system(sysname, CASES, VENDORS)
            m = metrics(res)
            rows.append(
                {
                    "system": sysname,
                    "accuracy %": m["accuracy"],
                    "unsafe": m["unsafe_missed_holds"],
                    "safety %": m["safety_pct"],
                    "false holds": m["false_holds"],
                }
            )
        progress.progress((i + 1) / len(dict.fromkeys(systems)))
    st.table(rows)
    st.caption(
        "`compromised` and `compromised_q` are adversarial harnesses: the model is steered to always "
        "report no change. They should show zero unsafe and a pile of false holds - the gate failing "
        "closed rather than open."
    )
