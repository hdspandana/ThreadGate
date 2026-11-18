"""Authenticated small-team workspace. No payment execution or release API."""
from __future__ import annotations
import json
import os
import sys
import time
import uuid
import pyotp
from datetime import datetime, timezone
from pathlib import Path
import streamlit as st
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from threadgate.workspace import Workspace, AccessDenied, Conflict
from threadgate.records import load_cases, load_vendors
from threadgate.pipeline import run_case
from threadgate.attestation import VerificationEvent
from threadgate.workspace_views import STATES
from threadgate.presentation import masked_text,mask_value,comparison_html,decision_banner_html

from threadgate.config import load_environment, key_configured
try:
    load_environment(ROOT,st.secrets)
except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
    load_environment(ROOT)
st.set_page_config(page_title='ThreadGate / Team Workspace',page_icon='◈',layout='wide')
st.markdown('<style>'+ (ROOT / 'app/theme.css').read_text()+'</style>',unsafe_allow_html=True)
st.markdown('''<div class="hero"><div class="eyebrow">THREADGATE / TEAM WORKSPACE</div>
<h1>One request.<br>A verifiable chain of action.</h1>
<p>Investigate → assign → independently verify → audit. Gate decisions stay separate from workflow status.</p>
<span class="pill">AUTHENTICATED ROLES</span><span class="pill">PERSISTENT CASES</span><span class="pill">NO PAYMENT EXECUTION</span></div>''',unsafe_allow_html=True)
try:
    service = Workspace(os.getenv('THREADGATE_WORKSPACE_DB',str(ROOT / 'data/runs/workspace.sqlite3')))
except Exception:
    st.error('Workspace storage unavailable. No verification or workflow action is available.')
    st.stop()
token = st.session_state.get('workspace_token','')
try:
    principal = service.principal(token)
except AccessDenied:
    st.session_state.pop('workspace_token',None)
    st.subheader('Sign in to your workspace')
    st.info('Team workspace: administrators manage accounts; analysts inspect requests; independent verifiers attest. For the synthetic walkthrough without accounts, run: python scripts/serve.py --demo --no-install')
    st.caption('Local accounts · optional authenticator MFA · 8-hour sessions · separate roles')
    with st.form('login',clear_on_submit=True):
        username = st.text_input('Username',max_chars=80)
        password = st.text_input('Password',type='password',max_chars=256)
        otp = st.text_input('Authenticator code (if MFA enabled)',max_chars=6)
        login = st.form_submit_button('Sign in',type='primary')
    if login:
        try:
            new_token = service.login(username,password,otp)
            st.session_state.clear()
            st.session_state.workspace_token = new_token
            st.rerun()
        except AccessDenied as exc:
            st.error(str(exc))
        except Exception:
            st.error('Sign-in unavailable. Contact the workspace operator.')
    st.code('python scripts/manage_workspace.py --username owner')
    st.caption('First install only: run this command locally to create an administrator. No default credentials. The public UI cannot bootstrap accounts.')
    st.stop()

st.sidebar.markdown('## ◈ ThreadGate')
st.sidebar.write(principal.username)
st.sidebar.caption(principal.role.upper()+' / SINGLE-ORGANISATION WORKSPACE')
if st.sidebar.button('Sign out'):
    service.logout(token)
    for key in list(st.session_state):
        del st.session_state[key]
    st.rerun()
pages = ['Shared inbox','My account','Process & limits']
if principal.role == 'analyst':
    pages.insert(1,'New investigation')
if principal.role == 'admin':
    pages.insert(1,'Team administration')
if principal.role in {'admin','auditor'}:
    pages.insert(1,'Workspace audit')
needs_enrolment = service.require_mfa and not service.mfa_status(token)
if needs_enrolment:
    pages = ['My account','Process & limits']
    st.sidebar.warning('MFA enrollment is required before workspace access.')
page = st.sidebar.radio('Workspace',pages)
reveal = st.sidebar.checkbox('Reveal sensitive values for this session',value=False,help='Recognised destinations are masked by default. This is not a full personal-data scrubber; pasted input remains visible while editing.')
def show_source(text):return text if reveal else masked_text(text)

st.sidebar.caption('No raw email or bank destination values are persisted in cases. This workspace is shared by one trusted organisation.')
vendors = load_vendors(ROOT / 'data/records/vendor_master.json')
fixtures = load_cases(ROOT / 'data/cases/frozen_v1.json') + load_cases(ROOT / 'data/cases/frozen_v2_additions.json')


def draft_input(prefix, vendor_id=None, fixture_id=None):
    if fixture_id and any(c['id']==fixture_id for c in fixtures):
        original = next(c for c in fixtures if c['id']==fixture_id)
        st.caption('Original synthetic corpus request recovered by its fixture identifier.')
        st.code(show_source(original['email']['body']),language=None)
        return original
    source = st.radio('Request source',['Synthetic scenario','Paste email'],horizontal=True,key=prefix+'source') if not vendor_id else 'Paste email'
    if source == 'Synthetic scenario':
        i = st.selectbox('Scenario',range(len(fixtures)),format_func=lambda i:fixtures[i]['id']+' / '+fixtures[i]['title'],key=prefix+'fixture')
        return fixtures[i]
    vid = vendor_id or st.selectbox('Trusted vendor',list(vendors),format_func=lambda v:vendors[v].display_name,key=prefix+'vendor')
    body = st.text_area('Original email body',max_chars=20000,height=160,key=prefix+'body')
    return {'vendor_id':vid,'email':{'body':body,'subject':'Pasted request','from':''}} if body.strip() else None


def inspect(case, mode):
    if mode == 'gemini':
        if not key_configured():
            raise Conflict('Configure GEMINI_API_KEY or GOOGLE_API_KEY. No offline fallback is used.')
        if time.monotonic()-st.session_state.get('last_model_call',0) < 2:
            raise Conflict('Wait two seconds between live requests.')
        st.session_state.last_model_call = time.monotonic()
    return run_case(case,vendors,extractor_mode=mode)

try:
    if page == 'Process & limits':
        st.subheader('The phased flow')
        st.markdown('''**1 / Administrator** creates separate analyst and verifier accounts.

**2 / Analyst** inspects a request and persists its minimal metadata and exact verification binding.

**3 / Analyst or administrator** assigns an active, independent verifier.

**4 / Assigned verifier** re-inspects the original request against the current trusted record,
confirms the callback and destination, and records an authenticated attestation.

**5 / Auditor** reviews transactional action history. `VERIFIED` means an authenticated
account attested; it does not prove the callback happened or authorise payment.

**Security boundaries:** a case revision prevents stale writes. Verification binds request,
vendor, destination digest, reference version, full source digest and full reference-content digest. Stale/missing references and changed
bindings cannot be verified. A rejected presentation consumes its event. Gate decisions
never downgrade on verification. Raw email is not persisted: real pasted requests must
be supplied again by the verifier through the trusted workflow.

**Deployment limits:** one organisation on one persistent host; local SQLite, local
password accounts with optional or enforced MFA, no SSO, no distributed abuse controls, no bank/ERP execution.
Audit entries are not externally anchored or tamper-proof. File administrators can
modify the database. Protect it, back it up, terminate TLS and restrict deployment
access. An independent security review is required before real financial use.''')
    elif page == 'My account':
        st.subheader('Account security')
        st.caption('Organisation MFA policy: '+('required' if service.require_mfa else 'optional'))
        with st.expander('Active sessions',expanded=False):
            sessions = service.own_sessions(token)
            st.dataframe([{'Session':s['session_id'][:12],'Current':s['current'],
                'Expires (UTC)':datetime.fromtimestamp(s['expires_at'],timezone.utc).isoformat()} for s in sessions],
                hide_index=True,width='stretch')
            st.caption('These are sessions, not verified device identities. Identifiers shown are not bearer tokens.')
            if st.button('Sign out all other sessions'):
                service.revoke_other_sessions(token)
                st.rerun()
            chosen_session = st.selectbox('Session to revoke',[s['session_id'] for s in sessions],
                format_func=lambda value:value[:12]+(' · current' if any(s['session_id']==value and s['current'] for s in sessions) else ''))
            if chosen_session and st.button('Revoke selected session'):
                current = any(s['session_id']==chosen_session and s['current'] for s in sessions)
                service.revoke_session(token,chosen_session)
                if current:
                    st.session_state.clear()
                st.rerun()
        enabled = service.mfa_status(token)
        st.write('Authenticator MFA:', 'Enabled' if enabled else 'Not enabled')
        if not enabled:
            with st.form('begin_mfa',clear_on_submit=True):
                password = st.text_input('Password to begin MFA setup',type='password',max_chars=256)
                if st.form_submit_button('Begin authenticator setup'):
                    st.session_state.mfa_pending = service.begin_mfa(token,password)
            if st.session_state.get('mfa_pending'):
                secret = st.session_state.mfa_pending
                st.warning('Private enrollment secret. Add it to your authenticator; never share screenshots. Setup expires after 10 minutes.')
                st.code(secret,language=None)
                with st.expander('Authenticator provisioning URI'):
                    st.code(pyotp.TOTP(secret).provisioning_uri(principal.username,issuer_name='ThreadGate'),language=None)
                with st.form('confirm_mfa',clear_on_submit=True):
                    code = st.text_input('Current six-digit code',max_chars=6)
                    if st.form_submit_button('Enable MFA and sign out'):
                        service.confirm_mfa(token,code)
                        st.session_state.clear()
                        st.rerun()
        elif not service.require_mfa:
            with st.form('disable_mfa',clear_on_submit=True):
                password = st.text_input('Password to disable MFA',type='password',max_chars=256)
                code = st.text_input('Fresh authenticator code (not already used for login)',max_chars=6)
                if st.form_submit_button('Disable MFA and revoke sessions'):
                    service.disable_mfa(token,password,code)
                    st.session_state.clear()
                    st.rerun()
        st.caption('Changing your password revokes all your sessions, including this one.')
        with st.form('change_password',clear_on_submit=True):
            old = st.text_input('Current password',type='password',max_chars=256)
            new = st.text_input('New password (14+ characters)',type='password',max_chars=256)
            confirm = st.text_input('Confirm new password',type='password',max_chars=256)
            if st.form_submit_button('Change password and sign out'):
                if new != confirm:
                    raise Conflict('New passwords do not match.')
                service.change_password(token,old,new)
                st.session_state.clear()
                st.rerun()
    elif page == 'Team administration':
        st.subheader('Team administration')
        st.dataframe(service.users(token),hide_index=True,width='stretch')
        with st.form('create_user',clear_on_submit=True):
            username = st.text_input('New username',max_chars=80)
            password = st.text_input('Initial password (14+ characters)',type='password',max_chars=256)
            role = st.selectbox('Role',['analyst','verifier','auditor','admin'])
            if st.form_submit_button('Create account'):
                service.create_user(token,username,password,role)
                st.success('Account created. Share credentials through a separate secure channel.')
        with st.form('disable_user',clear_on_submit=True):
            username = st.text_input('Account to disable')
            if st.form_submit_button('Disable account and revoke sessions'):
                service.disable_user(token,username)
                st.success('Account disabled and sessions revoked.')
    elif page == 'Workspace audit':
        st.subheader('Workspace audit')
        integrity = service.audit_integrity(token)
        st.info('Local audit / receipt integrity: '+integrity['status']+'. Not externally anchored; whole-store rewrites remain undetectable.')
        rows = service.audit(token)
        st.dataframe(rows,hide_index=True,width='stretch')
        st.download_button('Export audit JSON',json.dumps(rows,indent=2),'threadgate-audit.json','application/json')
        st.caption('Contains usernames, case identifiers and timestamps. Review before sharing. This is not a tamper-proof or externally anchored log.')
    elif page == 'New investigation':
        st.subheader('01 / Investigate a payment-change request')
        mode = st.selectbox('Extractor',['offline','gemini'],index=0,help='Offline makes no provider calls. Select Gemini explicitly only when you intend to spend API credits.')
        st.caption('Offline is a deterministic test double, not measured AI performance. Financial identifiers in corpus scenarios are synthetic.')
        case = draft_input('new')
        fingerprint = json.dumps(case,sort_keys=True)+mode
        if case and st.button('Inspect request',type='primary'):
            st.session_state.pop('pending_investigation',None)
            st.session_state.pop('submission_key',None)
            with st.spinner('Evaluating request against the current record…'):
                result = inspect(case,mode)
            st.session_state.pending_investigation = (fingerprint,result)
            st.session_state.submission_key = str(uuid.uuid4())
        pending = st.session_state.get('pending_investigation')
        if pending and pending[0]==fingerprint:
            result = pending[1]
            st.metric('Gate decision',result.decision.decision)
            st.markdown(decision_banner_html(result.decision.decision),unsafe_allow_html=True)
            st.caption('CLEAR means no change identified, not safe or approved. HOLD/REVIEW require human verification.')
            if result.error:
                st.warning('Extractor failure. Fail-closed HOLD; not a successful model evaluation.')
            st.markdown(comparison_html(result,reveal),unsafe_allow_html=True)
            for finding in result.decision.findings:
                st.write(finding.code+' · '+show_source(finding.message))
            with st.expander('Source email and validated evidence'):
                st.code(show_source(result.nt.text),language=None)
                for claim in result.validation.claims:
                    if claim.verified:
                        st.caption('Validated claim: '+claim.claim.field)
                        st.code(show_source(claim.claim.evidence),language=None)
                st.caption('Source and quotes are displayed for this session only, not persisted with the case.')
            if st.button('Save investigation to shared inbox'):
                case_id = service.submit(token,result,submission_key=st.session_state.submission_key)
                st.success('Saved case '+case_id+'. Open Shared inbox to assign a verifier.')
                st.session_state.pop('pending_investigation',None)
    else:
        st.subheader('Shared investigation inbox')
        counts = service.case_counts(token)
        a,b,c,d = st.columns(4)
        a.metric('Awaiting assignment',counts['OPEN'])
        b.metric('Assigned',counts['ASSIGNED'])
        c.metric('Verification recorded',counts['VERIFIED'])
        d.metric('Needs reinvestigation',counts['NEEDS_REINVESTIGATION'])
        left,middle,right = st.columns([2,1,1])
        query = left.text_input('Search inbox',max_chars=200,placeholder='Case ID, vendor, title or originating analyst')
        state = middle.selectbox('Workflow filter',['',*STATES],format_func=lambda value:value or 'All states')
        assigned_only = right.checkbox('Assigned to me')
        page_key = 'inbox_page_'+str((query,state,assigned_only))
        page_number = st.number_input('Page',min_value=1,max_value=100000,step=1,value=1,key=page_key)
        matches = service.search_cases(token,query=query,state=state,assigned_to=principal.username if assigned_only else '',page=int(page_number))
        rows = matches['items']
        st.caption(f"{matches['total']} matching cases · page {matches['page']} of {matches['pages']} · up to 25 per page")
        st.dataframe(rows,hide_index=True,width='stretch')
        if not rows:
            st.info('No cases on this page. Adjust filters or choose an earlier page; an analyst can submit a new investigation.')
            st.stop()
        case_id = st.selectbox('Open case',[r['id'] for r in rows],format_func=lambda i:next(r['title']+' / '+r['state']+' / '+i[:8] for r in rows if r['id']==i))
        record = service.get_case(token,case_id)
        report = record['report']
        a,b,c = st.columns(3)
        a.metric('Gate decision',report['gate_decision'])
        st.markdown(decision_banner_html(report['gate_decision']),unsafe_allow_html=True)
        b.metric('Workflow',record['state'])
        c.metric('Revision',record['revision'])
        st.caption('Created by '+record['created_by']+' · Assigned to '+(record['assigned_to'] or 'nobody'))
        st.caption('Verification never turns a HOLD into CLEAR and never authorises payment.')
        if record['state'] in {'OPEN','ASSIGNED'} and principal.role in {'admin','analyst'}:
            st.markdown('#### 02 / Assign independent verification')
            with st.form('assign'):
                verifier = st.text_input('Active verifier username',max_chars=80)
                if st.form_submit_button('Assign verifier'):
                    service.assign(token,case_id,verifier,record['revision'])
                    st.rerun()
        if principal.role=='verifier' and record['state']=='ASSIGNED' and record['assigned_to']==principal.username:
            st.markdown('#### 03 / Re-inspect and attest')
            st.caption('Reinspection is required because a reference or destination may have changed since submission. The checks execute on the server.')
            vendor = vendors.get(record['vendor_id'])
            if st.button('Return for reinvestigation — verification could not be completed'):
                service.return_for_reinvestigation(token,case_id,record['revision'])
                st.rerun()
            if vendor is None:
                st.warning('Trusted vendor record unavailable. Attestation is blocked; return this case for reinvestigation. Case history and exports remain available.')
                st.session_state.pop('verification_preview',None)
            else:
                original = draft_input('verify'+case_id,record['vendor_id'],report.get('case_id'))
                st.write('Trusted contact:',(vendor.current('contact_person') or 'Not recorded') if reveal else mask_value(vendor.current('contact_person')))
                st.write('Trusted phone:',(vendor.current('contact_phone') or 'Not recorded') if reveal else mask_value(vendor.current('contact_phone')))
                st.caption('Reveal sensitive values in the sidebar to use the trusted contact. Re-hide before screen sharing.')
                st.warning('Use the trusted contact, never replacement details from the request. Authenticated attestation records your statement; it cannot prove a call happened.')
                verification_input = json.dumps(original,sort_keys=True)+case_id+str(record['revision'])
                if original and st.button('Preview current destination and evidence'):
                    with st.spinner('Re-inspecting original request…'):
                        candidate = inspect(original,report['extractor'])
                    st.session_state.verification_preview = (verification_input,candidate)
                preview = st.session_state.get('verification_preview')
                preview_valid = bool(preview and preview[0]==verification_input and not preview[1].error)
                if preview_valid:
                    candidate = preview[1]
                    st.caption('Current reference: '+candidate.decision.reference_state+' / '+candidate.decision.reference_version)
                    st.markdown(comparison_html(candidate,reveal),unsafe_allow_html=True)
                    for claim in candidate.validation.claims:
                        if claim.verified:
                            st.code(show_source(claim.claim.evidence),language=None)
                st.caption('Final attestation runs one more inspection to check the current binding. With Gemini this is another API call; if interpretation changes the destination, verification is refused.')
                callback = st.checkbox('I completed out-of-band verification using an independently trusted contact')
                destination = st.checkbox('I verified the exact requested destination and current record version')
                if st.button('Re-inspect and record attestation',disabled=not (callback and destination and original and preview_valid),type='primary'):
                    with st.spinner('Rechecking current binding…'):
                        result = inspect(original,report['extractor'])
                    if result.error or result.verification != preview[1].verification:
                        raise Conflict('Reinspection failed or changed the viewed binding. Preview again; no verification accepted.')
                    context = result.verification
                    event = VerificationEvent(str(uuid.uuid4()),context.vendor_id,context.request_id,
                        context.destination_digest,context.reference_version,principal.username,datetime.now(timezone.utc).isoformat(),request_digest=context.request_digest,reference_digest=context.reference_digest)
                    outcome = service.verify(token,case_id,record['revision'],event,context,callback,destination,
                                             result.decision.reference_state=='CURRENT')
                    if not outcome.accepted:
                        st.error(outcome.message)
                    else:
                        st.rerun()
        with st.expander('Case audit timeline',expanded=True):
            st.dataframe(service.audit(token,case_id),hide_index=True,width='stretch')
        report = {**report,'workspace_case_id':case_id,'workflow_status':record['state'],
                  'revision':record['revision'],'created_by':record['created_by'],'assigned_to':record['assigned_to']}
        st.download_button('Export case metadata',json.dumps(report,indent=2),'threadgate-case.json','application/json')
        st.download_button('Export verification and audit bundle',json.dumps(service.export_case(token,case_id),indent=2),
            'threadgate-case-bundle.json','application/json')
        st.caption('Bundle omits raw destinations and email, but includes usernames, case/event IDs, timestamps and local integrity status. It is a consistent snapshot, not a signed or tamper-proof report. Review before sharing.')
except (AccessDenied,Conflict,ValueError) as exc:
    st.error(str(exc))
except Exception:
    st.error('Operation unavailable. No verification is confirmed by this screen. Refresh and check the case history before retrying.')
