"""ThreadGate verification workbench. Run: streamlit run app/workbench.py."""
from __future__ import annotations
import html
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from threadgate.records import load_cases, load_vendors
from threadgate.pipeline import run_case
from threadgate.attestation import VerificationEvent
from threadgate.durable import SQLiteAttestationStore
from threadgate.reporting import case_report
from threadgate.presentation import masked_text,mask_value,comparison_html,decision_banner_html

from threadgate.config import load_environment, key_configured
try:
    load_environment(ROOT,st.secrets)
except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
    load_environment(ROOT)
st.set_page_config(page_title='ThreadGate / Verification Workbench', page_icon='◈', layout='wide')
st.markdown('<style>'+(ROOT/'app/theme.css').read_text()+'</style>',unsafe_allow_html=True)
reveal = st.sidebar.checkbox('Reveal sensitive values for this session',value=False,help='Recognised destinations only; not a full personal-data scrubber. Pasted input remains visible while editing.')

vendors = load_vendors(ROOT / 'data/records/vendor_master.json')
cases = load_cases(ROOT / 'data/cases/frozen_v1.json') + load_cases(ROOT / 'data/cases/frozen_v2_additions.json')
st.sidebar.markdown('## ◈ ThreadGate')
st.sidebar.caption('PAYMENT CHANGE INTELLIGENCE')
page = st.sidebar.radio('Workspace', ['Investigate', 'Attack Lab', 'Evaluation', 'About'])
st.sidebar.divider()
mode = st.sidebar.selectbox('Interpretation engine', ['offline', 'gemini'],
    format_func=lambda x: 'Offline · deterministic test double' if x == 'offline' else 'Gemini · live API')
st.sidebar.caption('Offline results are not evidence of AI performance.')
st.sidebar.caption('API key configured' if key_configured() else 'No API key · offline exploration available')
st.sidebar.divider()
st.sidebar.caption('Synthetic financial data only. No bank connection. No payments executed.')
st.markdown('''<div class="hero"><div class="eyebrow">TRUST THE RECORD. NOT THE REQUEST.</div>
<h1>Verify the change.<br>Before money moves.</h1>
<p>AI reads the request. Deterministic controls compare it with trusted records. People verify the exceptions.</p>
<span class="pill">EVIDENCE-BOUND</span><span class="pill">FAIL-CLOSED</span><span class="pill">HUMAN VERIFICATION</span></div>''', unsafe_allow_html=True)

if page == 'About':
    st.subheader('A gate for the action, not a score for the email')
    st.markdown('''1. Normalise text and scan supported destination tokens.
2. Extract structured claims, with evidence.
3. Validate claims against the email and compare with the vendor record.
4. Apply deterministic, escalation-only controls.
5. Require out-of-band verification where indicated.

**CLEAR is not approval.** It means no change was identified by this prototype.

**Local durability is not identity.** This workbench uses transactional SQLite replay protection;
its synthetic verification events do not prove who performed a callback. There is no login or
payment release endpoint. Do not expose this as a production approval service.

Use a persistent local disk. Ephemeral hosting may erase the database on redeployment.
The separate `app/product.py` provides local accounts, roles and a persistent
team workflow. This unauthenticated workbench is synthetic-only. Neither
interface executes or approves payments; production identity and hosting need
independent review.''')
    st.stop()

if page == 'Evaluation':
    st.subheader('Evidence, with its boundaries visible')
    report = json.loads((ROOT / 'results/latest.json').read_text())
    a,b,c = st.columns(3)
    a.metric('Live model evaluated', 'Yes' if report.get('gemini_evaluated') else 'Not yet')
    b.metric('Reference date', report.get('as_of', 'Not recorded'))
    c.metric('Primary frozen cases', report['sets']['v1']['n_cases'])
    st.warning('Offline is a deterministic test double. Perfect offline results do not establish model performance or production safety.')
    for name, group in report['sets'].items():
        with st.expander(group['title'], expanded=name == 'v1'):
            st.caption(group.get('caveat', ''))
            rows = []
            for system, m in group.get('metrics', {}).items():
                rows.append({'System':system, 'Cases':m.get('n'), 'Accuracy %':m.get('accuracy'),
                             'Missed holds':m.get('unsafe_hold_releases'), 'Incorrect CLEAR':m.get('non_clear_releases'),
                             'False holds':m.get('false_holds')})
            st.dataframe(rows, hide_index=True, width="stretch")
    st.code('python eval/run_eval.py --require-gemini\npython -m pytest\npython scripts/kill_gate.py')
    st.download_button('Download checked-in evaluation', json.dumps(report, indent=2), 'threadgate-evaluation.json')
    st.stop()

if page == 'Attack Lab':
    st.subheader('Attack the interpretation. Inspect the boundary.')
    st.info('Adversarial extractors below are deterministic simulations of compromised model output, not live Gemini behaviour. No payment is executed.')
    with st.expander('Reproducible 16-category attack matrix'):
        st.caption('48 actual pipeline runs: offline test double and two deterministic compromised-output simulations. No provider calls; finite scanner coverage, not a security proof.')
        if st.button('Run synthetic attack matrix'):
            sys.path.insert(0,str(ROOT/'scripts'))
            from attack_report import generate
            st.session_state.attack_matrix = generate()
        matrix = st.session_state.get('attack_matrix')
        if matrix:
            st.write({'Runs':matrix['runs'],'Unsafe releases':matrix['unsafe_releases']})
            st.dataframe([{k:r[k] for k in ['category','engine','expected','actual','matches_label','unsafe_release']} for r in matrix['rows']],hide_index=True)
            row = st.selectbox('Inspect matrix row',range(len(matrix['rows'])),format_func=lambda i:matrix['rows'][i]['category']+' / '+matrix['rows'][i]['engine'])
            if reveal:st.json(matrix['rows'][row])
            else:st.caption('Row input, interpretation and trusted reference include sensitive values; use the explicit reveal control to inspect them.')
            st.download_button('Download synthetic attack matrix',json.dumps(matrix,indent=2),'threadgate-synthetic-attack-matrix.json')
            st.caption('Matrix downloads intentionally include synthetic source and references. Never use private input in this harness.')
    attack = st.selectbox('Adversarial harness', ['compromised', 'compromised_quote'])
    st.caption('The extractor tries to report no change. Supported independent controls still inspect the underlying email.')
else:
    attack = None
    st.subheader('Investigation desk')
    st.caption('1 · Choose a synthetic scenario or paste a request. 2 · Inspect it. 3 · Review evidence and the control trace before discussing verification.')

source = st.radio('Request source', ['Scenario inbox', 'Paste email'], horizontal=True)
if source == 'Scenario inbox':
    selected = st.selectbox('Select a synthetic request', range(len(cases)),
                           format_func=lambda i: f"{cases[i]['id']}  /  {cases[i]['title']}")
    case = cases[selected]
    st.caption('Corpus scenario · expected label is not an input to the gate')
else:
    vendor = st.selectbox('Trusted vendor record', list(vendors), format_func=lambda x: vendors[x].display_name)
    body = st.text_area('Untrusted email body', height=170, max_chars=20000,
                        placeholder='Paste a payment-change request…')
    # No constant id: the core derives a request binding from the actual email.
    case = {'vendor_id':vendor, 'email':{'body':body, 'from':'', 'subject':'Pasted request'}}
    if not body.strip():
        st.info('Paste an email to begin. Maximum 20,000 characters.')
        st.stop()

selected_mode = attack or mode
identity = json.dumps(case, sort_keys=True) + selected_mode
if st.button('◈  Inspect request', type='primary'):
    # A failed retry must never leave a previous successful result on screen.
    for key in ('inspection','workflow','demo_event','verification_outcome'):
        st.session_state.pop(key,None)
    if selected_mode == 'gemini' and not key_configured():
        st.error('Configure GEMINI_API_KEY or GOOGLE_API_KEY first. No offline fallback is used.')
    elif selected_mode == 'gemini' and time.monotonic() - st.session_state.get('last_api', 0) < 2:
        st.warning('Please wait two seconds between live model requests.')
    else:
        try:
            st.session_state.last_api = time.monotonic()
            with st.spinner('Scanning destinations and validating evidence…'):
                result = run_case(case, vendors, extractor_mode=selected_mode)
            st.session_state.inspection = (identity, result)
            st.session_state.workflow = 'PENDING' if result.decision.attestation_required else 'NOT_REQUIRED'
            st.session_state.pop('demo_event', None)
            st.session_state.pop('verification_outcome', None)
        except Exception:
            st.error('Inspection unavailable. Treat the request as HOLD and verify out of band. No payment action is available.')

saved = st.session_state.get('inspection')
if not saved or saved[0] != identity:
    st.caption('Choose Inspect request to produce a decision. Changing input invalidates the displayed result.')
    st.stop()
r = saved[1]
d = r.decision
if r.error:
    st.error('Extractor failed. This is a fail-closed result, not a successful AI evaluation.')
a,b,c,e = st.columns(4)
a.metric('Gate decision', d.decision)
b.metric('Reference', d.reference_state)
c.metric('Processing', f'{r.elapsed_ms:,.0f} ms')
e.metric('Workflow', st.session_state.workflow)
st.markdown(decision_banner_html(d.decision), unsafe_allow_html=True)
evidence_tab, controls_tab, verify_tab = st.tabs(['01 / Evidence & destination diff', '02 / Control trace', '03 / Verification & report'])
with evidence_tab:
    left,right = st.columns([1.05,1])
    with left:
        st.markdown('#### Source email')
        text = r.nt.text if reveal else masked_text(r.nt.text)
        # Exact-span highlighting; escape every untrusted fragment before HTML rendering.
        spans = sorted((v.span_norm for v in d.findings if v.span_norm), key=lambda x:x[0]) if reveal else []
        chunks, cursor = [], 0
        for start,end in spans:
            if start < cursor or start < 0 or end > len(text):
                continue
            chunks.extend([html.escape(text[cursor:start]), '<mark>'+html.escape(text[start:end])+'</mark>'])
            cursor = end
        chunks.append(html.escape(text[cursor:]))
        st.markdown('<div class="panel email">'+''.join(chunks)+'</div>', unsafe_allow_html=True)
    with right:
        st.markdown('#### Record → requested destination')
        st.markdown(comparison_html(r,reveal),unsafe_allow_html=True)
        st.caption(f'Reference version: {d.reference_version}')
        with st.expander('Structured extraction · untrusted until validated'):
            if reveal:st.json(r.extraction.model_dump())
            else:st.caption('Reveal sensitive values in the sidebar to view unmasked structured extraction.')
        for claim in r.validation.claims:
            if claim.verified:
                st.caption(f'Validated {claim.claim.field}')
                st.code(claim.claim.evidence if reveal else masked_text(claim.claim.evidence), language=None)
with controls_tab:
    st.markdown('#### Why the gate reached this decision')
    for f in d.findings:
        st.markdown(f'**{f.code}** · {"model-independent" if f.independent_of_model else "validated / policy input"}')
        st.write(f.message if reveal else masked_text(f.message))
    if not d.findings:
        st.caption('No finding was raised. Coverage remains limited to supported inputs and controls.')
    with st.expander('Decision reason codes'):
        st.json(d.reasons)
    if attack:
        if st.button('Compare against offline test double'):
            baseline = run_case(case, vendors, extractor_mode='offline')
            st.write({'Adversarial simulation': d.decision, 'Offline test double': baseline.decision.decision})
            st.caption('This comparison measures simulation behaviour only, not live model robustness.')
with verify_tab:
    st.warning('DEMO VERIFICATION ONLY · No authenticated identity, no proof of callback, no payment release. Gate decisions are never downgraded by this workflow.')
    vendor = vendors[r.vendor_id]
    st.markdown('#### Callback using the trusted record')
    st.write('Contact:',(vendor.current('contact_person') or 'Not recorded') if reveal else mask_value(vendor.current('contact_person')))
    st.write('Phone on file:',(vendor.current('contact_phone') or 'Not recorded — obtain independently') if reveal else mask_value(vendor.current('contact_phone')))
    st.caption('Never use a replacement contact supplied in the suspicious email.')
    for item in d.checklist:
        st.write('•', item if reveal else masked_text(item))
    confirmed = st.checkbox('Synthetic walkthrough: callback completed against the trusted contact')
    matches = st.checkbox('Synthetic walkthrough: exact requested destination and reference version checked')
    if d.attestation_required and r.verification:
        if st.button('Record synthetic verification', disabled=not (confirmed and matches)):
            context = r.verification
            event = VerificationEvent(str(uuid.uuid4()), context.vendor_id, context.request_id,
                context.destination_digest, context.reference_version, 'DEMO / unauthenticated', datetime.now(timezone.utc).isoformat(),request_digest=context.request_digest,reference_digest=context.reference_digest)
            try:
                store = SQLiteAttestationStore(os.getenv('THREADGATE_DB', str(ROOT / 'data/runs/attestations.sqlite3')))
                outcome = store.consume(event, context)
                st.session_state.demo_event = event
                st.session_state.workflow = 'DEMO_RECORDED' if outcome.accepted else 'REJECTED'
                st.session_state.verification_outcome = outcome.code
                st.rerun()
            except Exception:
                st.error('Storage unavailable. Verification was not confirmed. Keep the human-verification requirement outstanding.')
        if st.session_state.get('demo_event') and st.button('Test replay of the same event'):
            try:
                store = SQLiteAttestationStore(os.getenv('THREADGATE_DB', str(ROOT / 'data/runs/attestations.sqlite3')))
                replay = store.consume(st.session_state.demo_event, r.verification)
                st.info(replay.code + ' · ' + replay.message)
            except Exception:
                st.error('Storage unavailable; no verification accepted.')
    else:
        st.info('No attestation requested by this prototype. CLEAR is not payment approval.')
    if st.session_state.get('verification_outcome'):
        st.caption('Synthetic event result: ' + st.session_state.verification_outcome)
    report = case_report(r, st.session_state.workflow)
    st.download_button('↓ Export privacy-minimised case report', json.dumps(report, indent=2),
                       'threadgate-case-report.json', 'application/json')
    st.caption('Export omits email content, evidence quotations, contact details and destination values. Case/vendor identifiers remain; review before sharing.')
st.divider()
st.caption('ThreadGate / Security prototype · Local transactional replay protection · No bank integration · No automated reference updates')
