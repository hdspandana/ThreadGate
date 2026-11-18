"""Key-free completion: enforced MFA, sessions, idempotency, inbox and bundles."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import json
import uuid
import pyotp
import pytest
from threadgate.workspace import Workspace,AccessDenied,Conflict
from threadgate.clock import fixed
from threadgate.records import load_cases,load_vendors
from threadgate.pipeline import run_case
from threadgate.attestation import VerificationEvent
ROOT=Path(__file__).resolve().parents[1]
PASSWORD='testing-only-account-passphrase'


@pytest.fixture
def team(tmp_path):
    now=[1_000_000.0]
    service=Workspace(tmp_path/'completion.db',clock=lambda:now[0])
    service.bootstrap('owner',PASSWORD)
    tokens={'admin':service.login('owner',PASSWORD)}
    for role in ('analyst','verifier','auditor'):
        service.create_user(tokens['admin'],role,PASSWORD,role)
        tokens[role]=service.login(role,PASSWORD)
    vendors=load_vendors(ROOT/'data/records/vendor_master.json')
    case=load_cases(ROOT/'data/cases/frozen_v1.json')[0]
    result=run_case(case,vendors,extractor_mode='offline',clock=fixed('2026-10-06'))
    return service,tokens,now,result


def test_submission_key_is_idempotent_across_restart(team):
    service,tokens,now,result=team
    key=str(uuid.uuid4())
    first=service.submit(tokens['analyst'],result,submission_key=key)
    reopened=Workspace(service.path,clock=lambda:now[0])
    assert reopened.submit(tokens['analyst'],result,submission_key=key)==first
    assert len(reopened.list_cases(tokens['auditor']))==1
    assert len([r for r in service.audit(tokens['auditor'],first) if r['action']=='CASE_SUBMITTED'])==1


def test_concurrent_duplicate_submissions_have_one_case_and_one_audit(team):
    service,tokens,_,result=team
    key=str(uuid.uuid4())
    with ThreadPoolExecutor(max_workers=6) as workers:
        ids=list(workers.map(lambda _:service.submit(tokens['analyst'],result,submission_key=key),range(12)))
    assert len(set(ids))==1
    assert len(service.list_cases(tokens['auditor']))==1
    assert len(service.audit(tokens['auditor'],ids[0]))==1


def test_submission_key_cannot_rebind_changed_request_or_title(team):
    service,tokens,_,result=team
    key=str(uuid.uuid4())
    service.submit(tokens['analyst'],result,submission_key=key)
    with pytest.raises(Conflict):
        service.submit(tokens['analyst'],result,title='Different instruction',submission_key=key)
    result.nt.text+='\nAdditional payment instruction'
    with pytest.raises(Conflict):
        service.submit(tokens['analyst'],result,submission_key=key)


def test_submission_keys_are_scoped_to_actor_and_optional_for_new_cases(team):
    service,tokens,_,result=team
    service.create_user(tokens['admin'],'analyst-two',PASSWORD,'analyst')
    other=service.login('analyst-two',PASSWORD)
    key=str(uuid.uuid4())
    a=service.submit(tokens['analyst'],result,submission_key=key)
    b=service.submit(other,result,submission_key=key)
    c=service.submit(tokens['analyst'],result)
    assert len({a,b,c})==3


@pytest.mark.parametrize('key',['short','x'*129,5])
def test_invalid_submission_keys_rejected(team,key):
    service,tokens,_,result=team
    with pytest.raises(ValueError):
        service.submit(tokens['analyst'],result,submission_key=key)


def test_idempotency_is_atomic_with_audit(team,monkeypatch):
    service,tokens,_,result=team
    def fail(*a,**k):raise RuntimeError('simulated audit failure')
    monkeypatch.setattr(service,'_audit',fail)
    with pytest.raises(RuntimeError):
        service.submit(tokens['analyst'],result,submission_key=str(uuid.uuid4()))
    assert not service.list_cases(tokens['auditor'])
    with service._db() as db:
        assert db.execute('SELECT COUNT(*) FROM submission_keys').fetchone()[0]==0


def test_inbox_search_pagination_has_no_overlaps_at_equal_timestamps(team):
    service,tokens,_,result=team
    for i in range(31):service.submit(tokens['analyst'],result,title=f'Invoice batch {i}')
    page1=service.search_cases(tokens['auditor'],query='Invoice',page=1,page_size=20)
    page2=service.search_cases(tokens['auditor'],query='Invoice',page=2,page_size=20)
    assert page1['total']==31 and page1['pages']==2
    a={r['id'] for r in page1['items']};b={r['id'] for r in page2['items']}
    assert len(a)==20 and len(b)==11 and not a.intersection(b)
    assert service.case_counts(tokens['auditor'])['OPEN']==31


def test_inbox_filters_assignment_and_treats_wildcards_literally(team):
    service,tokens,_,result=team
    a=service.submit(tokens['analyst'],result,title='Invoice 100%_complete')
    service.submit(tokens['analyst'],result,title='Ordinary invoice')
    service.assign(tokens['admin'],a,'verifier',1)
    found=service.search_cases(tokens['verifier'],state='ASSIGNED',assigned_to='verifier')
    assert [r['id'] for r in found['items']]==[a]
    assert service.search_cases(tokens['auditor'],query='%_')['total']==1
    assert service.search_cases(tokens['auditor'],query="' OR 1=1 --")['total']==0
    assert service.search_cases(tokens['auditor'],query=a)['total']==1


@pytest.mark.parametrize('kwargs',[{'page':0},{'page':True},{'page_size':101},{'state':'BOGUS'},{'query':'x'*201}])
def test_invalid_inbox_parameters_rejected(team,kwargs):
    service,tokens,_,_=team
    with pytest.raises(ValueError):service.search_cases(tokens['auditor'],**kwargs)


def test_account_session_controls_do_not_expose_bearer_tokens(team):
    service,tokens,_,_=team
    other=service.login('analyst',PASSWORD)
    sessions=service.own_sessions(tokens['analyst'])
    assert len(sessions)==2
    assert other not in json.dumps(sessions) and tokens['analyst'] not in json.dumps(sessions)
    ref=next(r['session_id'] for r in sessions if not r['current'])
    with pytest.raises(AccessDenied):service.principal(ref)
    service.revoke_session(tokens['analyst'],ref)
    with pytest.raises(AccessDenied):service.principal(other)
    assert service.principal(tokens['analyst']).role=='analyst'


def test_user_cannot_revoke_another_accounts_session(team):
    service,tokens,_,_=team
    admin_ref=service.own_sessions(tokens['admin'])[0]['session_id']
    with pytest.raises(Conflict):service.revoke_session(tokens['analyst'],admin_ref)
    assert service.principal(tokens['admin']).role=='admin'


def test_sign_out_other_sessions_keeps_current_then_current_can_be_revoked(team):
    service,tokens,_,_=team
    service.login('analyst',PASSWORD);service.login('analyst',PASSWORD)
    assert service.revoke_other_sessions(tokens['analyst'])==2
    current=service.own_sessions(tokens['analyst'])[0]
    assert current['current']
    service.revoke_session(tokens['analyst'],current['session_id'])
    with pytest.raises(AccessDenied):service.principal(tokens['analyst'])


@pytest.mark.parametrize('operation',['list','search','counts','audit','users','get','export'])
def test_enforced_mfa_blocks_data_operations_but_permits_enrollment(team,operation):
    service,tokens,now,_=team
    secured=Workspace(service.path,clock=lambda:now[0],require_mfa=True)
    token=tokens['admin']
    assert secured.principal(token).role=='admin'
    assert not secured.mfa_status(token)
    calls={'list':lambda:secured.list_cases(token),'search':lambda:secured.search_cases(token),
           'counts':lambda:secured.case_counts(token),'audit':lambda:secured.audit(token),
           'users':lambda:secured.users(token),'get':lambda:secured.get_case(token,'missing'),
           'export':lambda:secured.export_case(token,'missing')}
    with pytest.raises(AccessDenied):calls[operation]()
    secret=secured.begin_mfa(token,PASSWORD)
    secured.confirm_mfa(token,pyotp.TOTP(secret).at(now[0]))
    now[0]+=31
    token=secured.login('owner',PASSWORD,pyotp.TOTP(secret).at(now[0]))
    assert secured.case_counts(token)['OPEN']==0
    with pytest.raises(AccessDenied):secured.disable_mfa(token,PASSWORD,'000000')


def test_invalid_enforcement_configuration_fails_closed(tmp_path,monkeypatch):
    monkeypatch.setenv('THREADGATE_REQUIRE_MFA','maybe')
    with pytest.raises(ValueError):Workspace(tmp_path/'invalid.db')
    from threadgate.config import check_settings
    assert any('REQUIRE_MFA' in issue for issue in check_settings())


def test_enforced_mfa_applies_to_submissions_and_account_management(team):
    service,tokens,now,result=team
    secured=Workspace(service.path,clock=lambda:now[0],require_mfa=True)
    with pytest.raises(AccessDenied):secured.submit(tokens['analyst'],result)
    with pytest.raises(AccessDenied):secured.create_user(tokens['admin'],'someone',PASSWORD,'analyst')
    assert secured.own_sessions(tokens['admin'])
    secured.logout(tokens['admin'])


def test_case_bundle_includes_verification_and_audit_not_private_values(team):
    service,tokens,_,result=team
    case_id=service.submit(tokens['analyst'],result)
    service.assign(tokens['analyst'],case_id,'verifier',1)
    c=result.verification
    event=VerificationEvent(str(uuid.uuid4()),c.vendor_id,c.request_id,c.destination_digest,c.reference_version,'verifier','now',request_digest=c.request_digest,reference_digest=c.reference_digest)
    assert service.verify(tokens['verifier'],case_id,2,event,c,True,True,True).accepted
    bundle=service.export_case(tokens['auditor'],case_id)
    assert bundle['case']['state']=='VERIFIED'
    assert bundle['report']['gate_decision']=='HOLD'
    assert bundle['verification_events'][0]['verifier']=='verifier'
    assert len(bundle['audit'])==3
    text=json.dumps(bundle)
    assert result.nt.text not in text and c.destination_digest not in text
    assert PASSWORD not in text and tokens['admin'] not in text
    for diff in result.decision.diffs:
        if diff.field=='account_number' and diff.new_value:assert diff.new_value not in text
    with pytest.raises(AccessDenied):service.export_case('invalid-token',case_id)
    with pytest.raises(Conflict):service.export_case(tokens['auditor'],'missing')


def test_mfa_enforced_ui_exposes_only_account_and_process(tmp_path,monkeypatch):
    from streamlit.testing.v1 import AppTest
    store=Workspace(tmp_path/'app.db',require_mfa=True)
    store.bootstrap('owner',PASSWORD)
    token=store.login('owner',PASSWORD)
    monkeypatch.setenv('THREADGATE_WORKSPACE_DB',store.path)
    monkeypatch.setenv('THREADGATE_REQUIRE_MFA','1')
    app=AppTest.from_file(str(ROOT/'app/product.py'))
    app.session_state['workspace_token']=token
    app.run(timeout=30)
    assert not app.exception
    assert list(app.sidebar.radio[0].options)==['My account','Process & limits']
    assert any(b.label=='Begin authenticator setup' for b in app.button)
    assert not any(b.label=='Create account' for b in app.button)


def test_sign_in_as_another_user_clears_previous_session_data(team,monkeypatch):
    from streamlit.testing.v1 import AppTest
    service,_,_,_=team
    live=Workspace(service.path)
    old=live.login('analyst',PASSWORD)
    live.logout(old)
    monkeypatch.setenv('THREADGATE_WORKSPACE_DB',service.path)
    app=AppTest.from_file(str(ROOT/'app/product.py'))
    app.session_state['workspace_token']=old
    app.session_state['sensitive_from_prior_user']='private synthetic state'
    app.run(timeout=30)
    next(w for w in app.text_input if w.label=='Username').set_value('auditor')
    next(w for w in app.text_input if w.label=='Password').set_value(PASSWORD)
    next(b for b in app.button if b.label=='Sign in').click().run(timeout=30)
    assert not app.exception
    assert 'sensitive_from_prior_user' not in app.session_state
    assert live.principal(app.session_state['workspace_token']).username=='auditor'
