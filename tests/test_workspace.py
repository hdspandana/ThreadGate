"""Phased product tests: identity -> cases -> independent attestation -> audit."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import json
import sqlite3
import uuid
import pytest
from threadgate.workspace import Workspace, AccessDenied, Conflict, password_hash, password_matches
from threadgate.pipeline import run_case
from threadgate.records import load_cases, load_vendors
from threadgate.attestation import VerificationEvent
from threadgate.clock import fixed

ROOT = Path(__file__).resolve().parents[1]
PASSWORD = 'testing-only-long-passphrase'


@pytest.fixture
def result():
    vendors = load_vendors(ROOT / 'data/records/vendor_master.json')
    case = load_cases(ROOT / 'data/cases/frozen_v1.json')[0]
    return run_case(case,vendors,extractor_mode='offline',clock=fixed('2026-10-06'))


@pytest.fixture
def team(tmp_path):
    now = [1000000.0]
    service = Workspace(tmp_path / 'workspace.db',clock=lambda:now[0])
    service.bootstrap('owner',PASSWORD)
    tokens = {'admin':service.login('owner',PASSWORD)}
    for role in ('analyst','verifier','auditor'):
        service.create_user(tokens['admin'],role,PASSWORD,role)
        tokens[role] = service.login(role,PASSWORD)
    return service,tokens,now


def prepared(team,result):
    service,tokens,_ = team
    case_id = service.submit(tokens['analyst'],result)
    service.assign(tokens['analyst'],case_id,'verifier',1)
    c = result.verification
    event = VerificationEvent(str(uuid.uuid4()),c.vendor_id,c.request_id,c.destination_digest,c.reference_version,'verifier','now',request_digest=c.request_digest,reference_digest=c.reference_digest)
    return case_id,event


def test_password_hash_salted_and_verified():
    a,b = password_hash(PASSWORD),password_hash(PASSWORD)
    assert a != b
    assert password_matches(PASSWORD,a)
    assert not password_matches('wrong',a)
    assert PASSWORD not in a


@pytest.mark.parametrize('password',['short','x'*257])
def test_password_policy(password):
    with pytest.raises(ValueError):
        password_hash(password)


def test_bootstrap_only_once(team):
    service,_,_ = team
    with pytest.raises(Conflict):
        service.bootstrap('another',PASSWORD)


def test_session_token_not_stored_in_plaintext(team):
    service,tokens,_ = team
    with sqlite3.connect(service.path) as db:
        dump = '\n'.join(db.iterdump())
    assert tokens['admin'] not in dump
    assert PASSWORD not in dump


def test_session_expiry_and_revocation(team):
    service,tokens,now = team
    service.logout(tokens['analyst'])
    with pytest.raises(AccessDenied):
        service.principal(tokens['analyst'])
    now[0] += 8*60*60+1
    with pytest.raises(AccessDenied):
        service.principal(tokens['admin'])


def test_disabled_user_loses_existing_sessions(team):
    service,tokens,_ = team
    service.disable_user(tokens['admin'],'analyst')
    with pytest.raises(AccessDenied):
        service.principal(tokens['analyst'])
    with pytest.raises(AccessDenied):
        service.login('analyst',PASSWORD)


def test_admin_cannot_disable_self(team):
    service,tokens,_ = team
    with pytest.raises(Conflict):
        service.disable_user(tokens['admin'],'owner')


def test_lockout_is_persisted_and_expires(team):
    service,_,now = team
    for _ in range(5):
        with pytest.raises(AccessDenied):
            service.login('analyst','wrong')
    with pytest.raises(AccessDenied):
        service.login('analyst',PASSWORD)
    now[0] += 901
    assert service.login('analyst',PASSWORD)


@pytest.mark.parametrize('role',['analyst','verifier','auditor'])
def test_only_admin_can_manage_accounts(team,role):
    service,tokens,_ = team
    with pytest.raises(AccessDenied):
        service.create_user(tokens[role],'intruder',PASSWORD,'admin')
    with pytest.raises(AccessDenied):
        service.disable_user(tokens[role],'owner')
    with pytest.raises(AccessDenied):
        service.users(tokens[role])


@pytest.mark.parametrize('role',['admin','verifier','auditor'])
def test_only_analyst_submits(team,result,role):
    service,tokens,_ = team
    with pytest.raises(AccessDenied):
        service.submit(tokens[role],result)


def test_case_survives_restart_without_email_or_destination(team,result):
    service,tokens,now = team
    case_id = service.submit(tokens['analyst'],result)
    restarted = Workspace(service.path,clock=lambda:now[0])
    stored = restarted.get_case(tokens['auditor'],case_id)
    assert stored['state']=='OPEN'
    import subprocess, sys
    backup = Path(service.path).parent / 'private.sqlite3.backup'
    subprocess.run([sys.executable,str(ROOT/'scripts/backup_workspace.py'),'--db',service.path,'--output',str(backup)],check=True,capture_output=True)
    with sqlite3.connect(backup) as db:
        assert db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM cases').fetchone()[0]==1
        assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    serialized = json.dumps(stored)
    assert result.nt.text not in serialized
    for diff in result.decision.diffs:
        if diff.field == 'account_number' and diff.new_value:
            assert diff.new_value not in serialized


def test_assignment_requires_active_verifier_and_revision(team,result):
    service,tokens,_ = team
    case_id = service.submit(tokens['analyst'],result)
    with pytest.raises(Conflict):
        service.assign(tokens['admin'],case_id,'analyst',1)
    service.assign(tokens['admin'],case_id,'verifier',1)
    with pytest.raises(Conflict):
        service.assign(tokens['admin'],case_id,'verifier',1)


def test_analyst_cannot_assign_other_analysts_case(team,result):
    service,tokens,_ = team
    service.create_user(tokens['admin'],'other-analyst',PASSWORD,'analyst')
    other = service.login('other-analyst',PASSWORD)
    case_id = service.submit(tokens['analyst'],result)
    with pytest.raises(AccessDenied):
        service.assign(other,case_id,'verifier',1)


def test_concurrent_assignment_has_one_winner(team,result):
    service,tokens,_ = team
    case_id = service.submit(tokens['analyst'],result)
    def assign(_):
        try:
            service.assign(tokens['admin'],case_id,'verifier',1)
            return True
        except Conflict:
            return False
    with ThreadPoolExecutor(max_workers=4) as executor:
        assert sum(executor.map(assign,range(4))) == 1


@pytest.mark.parametrize('role',['admin','analyst','auditor'])
def test_non_verifiers_cannot_attest(team,result,role):
    service,tokens,_ = team
    case_id,event = prepared(team,result)
    with pytest.raises(AccessDenied):
        service.verify(tokens[role],case_id,2,event,result.verification,True,True,True)


def test_independent_verification_preserves_hold_and_is_audited(team,result):
    service,tokens,_ = team
    case_id,event = prepared(team,result)
    outcome = service.verify(tokens['verifier'],case_id,2,event,result.verification,True,True,True)
    assert outcome.accepted
    record = service.get_case(tokens['auditor'],case_id)
    assert record['state']=='VERIFIED'
    assert record['report']['gate_decision']=='HOLD'
    assert any(r['action']=='VERIFICATION_ACCEPTED' for r in service.audit(tokens['auditor'],case_id))
    with pytest.raises(Conflict):
        service.verify(tokens['verifier'],case_id,2,event,result.verification,True,True,True)


@pytest.mark.parametrize('field,value',[('reference_version','new-version'),('destination_digest','changed'),('request_id','other-request')])
def test_changed_live_binding_is_rejected(team,result,field,value):
    service,tokens,_ = team
    case_id,event = prepared(team,result)
    with pytest.raises(Conflict):
        service.verify(tokens['verifier'],case_id,2,event,replace(result.verification,**{field:value}),True,True,True)
    assert service.get_case(tokens['auditor'],case_id)['state']=='ASSIGNED'


def test_stale_reference_not_verified(team,result):
    service,tokens,_ = team
    case_id,event = prepared(team,result)
    with pytest.raises(Conflict):
        service.verify(tokens['verifier'],case_id,2,event,result.verification,True,True,False)


def test_checklist_required(team,result):
    service,tokens,_ = team
    case_id,event = prepared(team,result)
    with pytest.raises(Conflict):
        service.verify(tokens['verifier'],case_id,2,event,result.verification,False,True,True)


def test_wrong_actor_rejected(team,result):
    service,tokens,_ = team
    case_id,event = prepared(team,result)
    with pytest.raises(AccessDenied):
        service.verify(tokens['verifier'],case_id,2,replace(event,attested_by='owner'),result.verification,True,True,True)


def test_binding_rejection_burns_event_transactionally(team,result):
    service,tokens,_ = team
    case_id,event = prepared(team,result)
    bad = replace(event,destination_digest='wrong')
    assert not service.verify(tokens['verifier'],case_id,2,bad,result.verification,True,True,True).accepted
    with pytest.raises(Conflict):
        service.verify(tokens['verifier'],case_id,2,event,result.verification,True,True,True)
    assert service.get_case(tokens['auditor'],case_id)['state']=='ASSIGNED'


def test_audit_failure_rolls_back_verification(team,result,monkeypatch):
    service,tokens,_ = team
    case_id,event = prepared(team,result)
    def fail(*args,**kwargs):
        raise sqlite3.OperationalError('simulated storage failure')
    monkeypatch.setattr(service,'_audit',fail)
    with pytest.raises(sqlite3.OperationalError):
        service.verify(tokens['verifier'],case_id,2,event,result.verification,True,True,True)
    assert service.get_case(tokens['auditor'],case_id)['state']=='ASSIGNED'
    with sqlite3.connect(service.path) as db:
        assert db.execute('SELECT COUNT(*) FROM workflow_events').fetchone()[0]==0


def test_workspace_audit_privileged_case_audit_shared(team,result):
    service,tokens,_ = team
    case_id,_ = prepared(team,result)
    with pytest.raises(AccessDenied):
        service.audit(tokens['analyst'])
    assert service.audit(tokens['analyst'],case_id)
    assert service.audit(tokens['auditor'])


def test_unauthenticated_reads_denied(team):
    service,_,_ = team
    with pytest.raises(AccessDenied):
        service.list_cases('invented')
    with pytest.raises(AccessDenied):
        service.get_case('invented','invented')
    with pytest.raises(AccessDenied):
        service.audit('invented')


def test_product_login_page_has_no_case_content(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv('THREADGATE_WORKSPACE_DB',str(tmp_path / 'app.db'))
    app = AppTest.from_file(str(ROOT / 'app/product.py')).run(timeout=30)
    assert not app.exception
    assert not app.dataframe
    assert any('Sign in' in b.label for b in app.button)


def test_product_authenticated_analyst_flow(team,tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    service,_,_ = team
    # App uses the real clock, so create a session with that clock for UI testing.
    live = Workspace(service.path)
    token = live.login('analyst',PASSWORD)
    monkeypatch.setenv('THREADGATE_WORKSPACE_DB',service.path)
    app = AppTest.from_file(str(ROOT / 'app/product.py'))
    app.session_state['workspace_token'] = token
    app.run(timeout=30)
    assert not app.exception
    app.sidebar.radio[0].set_value('New investigation').run()
    app.selectbox[0].set_value('offline').run()
    next(b for b in app.button if b.label=='Inspect request').click().run()
    assert not app.exception
    next(b for b in app.button if b.label=='Save investigation to shared inbox').click().run()
    assert not app.exception
    assert len(live.list_cases(token))==1
    case_id = live.list_cases(token)[0]['id']
    live.assign(token,case_id,'verifier',1)
    # Pin freshness in this UI regression so it does not fail as demo records age.
    import threadgate.pipeline as pipeline
    original_run = pipeline.run_case
    monkeypatch.setattr(pipeline,'run_case',lambda *a,**k: original_run(*a,**k,clock=fixed('2026-10-06')))
    verifier = AppTest.from_file(str(ROOT / 'app/product.py'))
    verifier.session_state['workspace_token'] = live.login('verifier',PASSWORD)
    verifier.run(timeout=30)
    assert not verifier.exception
    next(b for b in verifier.button if b.label=='Preview current destination and evidence').click().run(timeout=30)
    assert not verifier.exception
    for checkbox in verifier.checkbox:
        checkbox.check()
    verifier.run()
    next(b for b in verifier.button if b.label=='Re-inspect and record attestation').click().run(timeout=30)
    assert not verifier.exception
    assert live.get_case(token,case_id)['state']=='VERIFIED'
    auditor = AppTest.from_file(str(ROOT / 'app/product.py'))
    auditor.session_state['workspace_token'] = live.login('auditor',PASSWORD)
    auditor.run(timeout=30)
    auditor.sidebar.radio[0].set_value('Workspace audit').run()
    assert not auditor.exception
    assert auditor.dataframe


def test_password_change_revokes_all_sessions(team):
    service,tokens,_ = team
    second = service.login('analyst',PASSWORD)
    with pytest.raises(AccessDenied):
        service.change_password(tokens['analyst'],'wrong',PASSWORD+'-new')
    service.change_password(tokens['analyst'],PASSWORD,PASSWORD+'-new')
    for token in (tokens['analyst'],second):
        with pytest.raises(AccessDenied):
            service.principal(token)
    assert service.login('analyst',PASSWORD+'-new')


def test_return_for_reinvestigation_preserves_gate(team,result):
    service,tokens,_ = team
    case_id,_ = prepared(team,result)
    service.return_for_reinvestigation(tokens['verifier'],case_id,2)
    record = service.get_case(tokens['analyst'],case_id)
    assert record['state']=='NEEDS_REINVESTIGATION'
    assert record['report']['gate_decision']=='HOLD'
    with pytest.raises(Conflict):
        service.assign(tokens['admin'],case_id,'verifier',3)


def test_other_verifier_cannot_attest_assigned_case(team,result):
    service,tokens,_ = team
    case_id,event = prepared(team,result)
    service.create_user(tokens['admin'],'other-verifier',PASSWORD,'verifier')
    other = service.login('other-verifier',PASSWORD)
    with pytest.raises(AccessDenied):
        service.verify(other,case_id,2,replace(event,attested_by='other-verifier'),result.verification,True,True,True)


def test_concurrent_verification_has_one_winner(team,result):
    service,tokens,_ = team
    case_id,event = prepared(team,result)
    def verify(_):
        try:
            return service.verify(tokens['verifier'],case_id,2,event,result.verification,True,True,True).accepted
        except Conflict:
            return False
    with ThreadPoolExecutor(max_workers=4) as executor:
        assert sum(executor.map(verify,range(4))) == 1
    assert len([r for r in service.audit(tokens['auditor'],case_id) if r['action']=='VERIFICATION_ACCEPTED'])==1


def test_unknown_roles_and_duplicate_accounts_rejected(team):
    service,tokens,_ = team
    with pytest.raises(ValueError):
        service.create_user(tokens['admin'],'someone',PASSWORD,'superuser')
    with pytest.raises(Conflict):
        service.create_user(tokens['admin'],'analyst',PASSWORD,'admin')
