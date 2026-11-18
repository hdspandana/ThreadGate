"""Key-independent readiness: MFA, secrets, preflight and live acceptance tooling."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import pyotp
import pytest
from threadgate.config import load_environment,key_configured,check_settings
from threadgate.workspace import Workspace,AccessDenied,Conflict
ROOT=Path(__file__).resolve().parents[1]
PASSWORD='local-testing-long-passphrase'


def script(name):
    spec=importlib.util.spec_from_file_location('readiness_'+name,ROOT/'scripts'/(name+'.py'))
    mod=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def identity(tmp_path):
    now=[1_000_000.0]
    store=Workspace(tmp_path/'mfa.db',clock=lambda:now[0])
    store.bootstrap('owner',PASSWORD)
    token=store.login('owner',PASSWORD)
    return store,token,now


def enable(identity):
    store,token,now=identity
    secret=store.begin_mfa(token,PASSWORD)
    store.confirm_mfa(token,pyotp.TOTP(secret).at(now[0]))
    now[0]+=31
    return secret


def test_mfa_requires_correct_password_for_enrolment(identity):
    store,token,_=identity
    with pytest.raises(AccessDenied):
        store.begin_mfa(token,'incorrect')


def test_mfa_confirmation_revokes_sessions_and_requires_new_factor(identity):
    store,token,now=identity
    secret=enable(identity)
    with pytest.raises(AccessDenied):
        store.principal(token)
    with pytest.raises(AccessDenied):
        store.login('owner',PASSWORD)
    assert store.login('owner',PASSWORD,pyotp.TOTP(secret).at(now[0]))


def test_mfa_codes_are_single_use_and_next_step_works(identity):
    store,_,now=identity
    secret=enable(identity)
    code=pyotp.TOTP(secret).at(now[0])
    token=store.login('owner',PASSWORD,code)
    assert store.mfa_status(token)
    with pytest.raises(AccessDenied):
        store.login('owner',PASSWORD,code)
    now[0]+=31
    assert store.login('owner',PASSWORD,pyotp.TOTP(secret).at(now[0]))


def test_mfa_setup_expires(identity):
    store,token,now=identity
    secret=store.begin_mfa(token,PASSWORD)
    now[0]+=601
    with pytest.raises(AccessDenied):
        store.confirm_mfa(token,pyotp.TOTP(secret).at(now[0]))
    assert not store.mfa_status(token)


def test_mfa_disable_requires_fresh_factor_and_revokes_sessions(identity):
    store,_,now=identity
    secret=enable(identity)
    token=store.login('owner',PASSWORD,pyotp.TOTP(secret).at(now[0]))
    with pytest.raises(AccessDenied):
        store.disable_mfa(token,PASSWORD,pyotp.TOTP(secret).at(now[0]))
    now[0]+=31
    store.disable_mfa(token,PASSWORD,pyotp.TOTP(secret).at(now[0]))
    with pytest.raises(AccessDenied):
        store.principal(token)
    assert store.login('owner',PASSWORD)


def test_mfa_secret_not_in_audit(identity,monkeypatch):
    store,_,now=identity
    secret=enable(identity)
    token=store.login('owner',PASSWORD,pyotp.TOTP(secret).at(now[0]))
    assert secret not in json.dumps(store.audit(token))
    with pytest.raises(Conflict):
        store.begin_mfa(token,PASSWORD)
    recovery=script('recover_account')
    monkeypatch.setenv('THREADGATE_WORKSPACE_DB',store.path)
    monkeypatch.setattr(recovery,'Workspace',lambda path:store)
    monkeypatch.setattr('builtins.input',lambda prompt:'owner')
    monkeypatch.setattr(recovery.getpass,'getpass',lambda prompt:PASSWORD+'-new')
    monkeypatch.setattr(sys,'argv',['recover_account','--username','owner','--reset-mfa'])
    recovery.main()
    with pytest.raises(AccessDenied):
        store.principal(token)
    recovered=store.login('owner',PASSWORD+'-new')
    assert not store.mfa_status(recovered)
    assert any(row['action']=='ACCOUNT_RECOVERED' for row in store.audit(recovered))


def test_existing_workspace_is_migrated_additively(identity):
    store,token,now=identity
    with store._db(write=True) as db:
        db.execute('DROP TABLE user_mfa')
        db.execute('DROP TABLE submission_keys')
        db.execute('PRAGMA user_version=1')
    reopened=Workspace(store.path,clock=lambda:now[0])
    assert not reopened.mfa_status(token)
    assert reopened.principal(token).role=='admin'
    with reopened._db() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==3
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name='submission_keys'").fetchone()
    with reopened._db(write=True) as db:
        db.execute('PRAGMA user_version=99')
    with pytest.raises(Conflict):
        Workspace(store.path,clock=lambda:now[0])


def test_env_file_loads_and_environment_wins(tmp_path,monkeypatch):
    monkeypatch.delenv('THREADGATE_SKIP_DOTENV',raising=False)
    monkeypatch.setenv('GEMINI_API_KEY','')
    monkeypatch.delenv('GEMINI_API_KEY')
    monkeypatch.delenv('GOOGLE_API_KEY',raising=False)
    (tmp_path/'.env').write_text('GEMINI_API_KEY='+'test-key-not-real\nTHREADGATE_MODEL=file-model\n')
    monkeypatch.setenv('THREADGATE_MODEL','environment-model')
    load_environment(tmp_path)
    assert key_configured()
    assert __import__('os').environ['THREADGATE_MODEL']=='environment-model'
    monkeypatch.delenv('GEMINI_API_KEY')


def test_placeholder_key_is_not_configured(tmp_path,monkeypatch):
    monkeypatch.setenv('GEMINI_API_KEY','your-key-here')
    monkeypatch.delenv('GOOGLE_API_KEY',raising=False)
    load_environment(tmp_path)
    assert not key_configured()
    monkeypatch.setenv('THREADGATE_SKIP_DOTENV','0')
    monkeypatch.setenv('GEMINI_API_KEY','your-key-here')
    load_environment(tmp_path,{'GEMINI_API_KEY':'cloud-key-not-real'})
    assert key_configured()


def test_offline_mode_does_not_load_dotenv_or_cloud_secrets(tmp_path,monkeypatch):
    monkeypatch.setenv('THREADGATE_SKIP_DOTENV','1')
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY',raising=False)
    (tmp_path/'.env').write_text('GEMINI_API_KEY='+'test-key-not-real')
    load_environment(tmp_path,{'GEMINI_API_KEY':'cloud-key-not-real'})
    assert not key_configured()


@pytest.mark.parametrize('value',['zero','0','-1','999999'])
def test_invalid_timeout_detected(monkeypatch,value):
    monkeypatch.setenv('THREADGATE_HTTP_TIMEOUT_MS',value)
    assert any('HTTP_TIMEOUT' in issue for issue in check_settings())


def test_live_check_without_key_never_calls_provider(tmp_path,monkeypatch):
    mod=script('live_check')
    monkeypatch.setenv('THREADGATE_SKIP_DOTENV','1')
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY',raising=False)
    monkeypatch.setattr(mod,'run_checks',lambda:pytest.fail('Must not run without a key'))
    target=tmp_path/'live.json'
    assert mod.main(['--output',str(target)])==2
    assert not target.exists()


def test_live_check_smoke_uses_real_pipeline_with_mocked_extractor(monkeypatch):
    mod=script('live_check')
    from threadgate.pipeline import run_case
    from threadgate.extract import offline_extract
    monkeypatch.setattr(mod,'run_case',lambda *a,**kw:run_case(*a,**kw,extractor_fn=offline_extract))
    report=mod.run_checks()
    assert report['status']=='PASS'
    assert len(report['cases'])==3
    assert all(row['passed'] for row in report['cases'])


def valid_report():
    return {'gemini_evaluated':True,'systems_run':['gemini'],'systems_invalid':[],
            'sets':{name:{'metrics':{'gemini':{'n':20,'unsafe_hold_releases':0,'non_clear_releases':0}}}
                    for name in ('v1','stress','combined')}}


def test_live_report_acceptance_passes_valid_finite_run():
    assert not script('check_live_report').issues(valid_report())


@pytest.mark.parametrize('kind',['missing','invalid','unsafe','absent_metric'])
def test_live_report_acceptance_rejects_incomplete_or_unsafe(kind):
    report=valid_report()
    if kind=='missing':
        report['gemini_evaluated']=False
    elif kind=='invalid':
        report['systems_invalid']=['gemini']
    elif kind=='unsafe':
        report['sets']['v1']['metrics']['gemini']['non_clear_releases']=1
    else:
        del report['sets']['combined']['metrics']['gemini']['unsafe_hold_releases']
    assert script('check_live_report').issues(report)


def test_release_plan_has_no_live_api_command():
    mod=script('release_check')
    assert all('live_check.py' not in ' '.join(args) and '--require-gemini' not in args for _,args in mod.commands())


def test_source_package_excludes_local_credentials_and_databases(tmp_path,monkeypatch):
    mod=script('package_release')
    monkeypatch.setattr(mod,'ROOT',tmp_path)
    for path in ('.env','.streamlit/secrets.toml','data/runs/workspace.sqlite3','app/.env.production','deployment/private.pem','app/database.sqlite3-wal'):
        file=tmp_path/path
        file.parent.mkdir(parents=True,exist_ok=True)
        file.write_text('private')
        assert not mod.included(file)
    lock=tmp_path/'requirements.lock'
    lock.write_text('pyotp==2.9.0')
    assert mod.included(lock)
    init=script('init_env')
    monkeypatch.setattr(init,'ROOT',tmp_path)
    assert init.main()==0
    assert (tmp_path/'.env').read_text()=='private'
    (tmp_path/'.env').unlink()
    (tmp_path/'.env.example').write_text('placeholder-only')
    assert init.main()==0
    assert (tmp_path/'.env').read_text()=='placeholder-only'
    if sys.platform!='win32':
        assert (tmp_path/'.env').stat().st_mode & 0o777 == 0o600


def test_git_ignored_local_secret_can_be_excluded_but_tracked_secret_cannot(tmp_path,monkeypatch):
    mod=script('secret_scan')
    monkeypatch.setattr(mod,'ROOT',tmp_path)
    subprocess.run(['git','init','-q'],cwd=tmp_path,check=True)
    (tmp_path/'.gitignore').write_text('.env\n.streamlit/secrets.toml\n__pycache__\n')
    (tmp_path/'.env').write_text('local')
    assert mod.scan_working_tree()
    assert not mod.scan_working_tree(allow_local_secrets=True)
    subprocess.run(['git','add','-f','.env'],cwd=tmp_path,check=True)
    assert mod.scan_working_tree(allow_local_secrets=True)


def test_preflight_never_calls_live_api(monkeypatch,tmp_path):
    mod=script('doctor')
    monkeypatch.setenv('THREADGATE_SKIP_DOTENV','1')
    monkeypatch.setenv('THREADGATE_WORKSPACE_DB',str(tmp_path/'workspace.db'))
    monkeypatch.delenv('GEMINI_API_KEY',raising=False)
    monkeypatch.delenv('GOOGLE_API_KEY',raising=False)
    report=mod.inspect()
    assert report['status']=='PASS'
    assert report['live_api_tested'] is False
    assert mod.inspect(require_key=True)['status']=='FAIL'


def test_product_mfa_enrolment_ui(identity,monkeypatch):
    from streamlit.testing.v1 import AppTest
    store,_,_=identity
    live=Workspace(store.path)
    monkeypatch.setenv('THREADGATE_WORKSPACE_DB',store.path)
    app=AppTest.from_file(str(ROOT/'app/product.py'))
    app.session_state['workspace_token']=live.login('owner',PASSWORD)
    app.run(timeout=30)
    app.sidebar.radio[0].set_value('My account').run()
    assert not app.exception
    assert any(b.label=='Begin authenticator setup' for b in app.button)


def test_retention_dry_run_archives_terminal_metadata_not_replay_or_open_cases(identity):
    store,admin,now=identity
    from threadgate.records import load_cases,load_vendors
    from threadgate.pipeline import run_case
    from threadgate.clock import fixed
    from threadgate.attestation import VerificationEvent
    vendors=load_vendors(ROOT/'data/records/vendor_master.json')
    case=load_cases(ROOT/'data/cases/frozen_v1.json')[0]
    result=run_case(case,vendors,extractor_mode='offline',clock=fixed('2026-10-06'))
    store.create_user(admin,'analyst',PASSWORD,'analyst')
    store.create_user(admin,'verifier',PASSWORD,'verifier')
    analyst=store.login('analyst',PASSWORD)
    verifier=store.login('verifier',PASSWORD)
    completed=store.submit(analyst,result)
    still_open=store.submit(analyst,result)
    store.assign(analyst,completed,'verifier',1)
    c=result.verification
    event=VerificationEvent('retention-event',c.vendor_id,c.request_id,c.destination_digest,c.reference_version,'verifier','now',request_digest=c.request_digest,reference_digest=c.reference_digest)
    assert store.verify(verifier,completed,2,event,c,True,True,True).accepted
    now[0]+=91*86400
    retention=script('retention')
    assert retention.archive_terminal(store,90)['eligible_cases']==1
    with store._db() as db:
        assert db.execute('SELECT state FROM cases WHERE id=?',(completed,)).fetchone()[0]=='VERIFIED'
    assert retention.archive_terminal(store,90,apply=True)['eligible_cases']==1
    with store._db() as db:
        row=db.execute('SELECT * FROM cases WHERE id=?',(completed,)).fetchone()
        assert row['state']=='ARCHIVED' and row['context']=='{}'
        assert json.loads(row['report'])['gate_decision']=='HOLD'
        assert db.execute('SELECT COUNT(*) FROM workflow_events').fetchone()[0]==1
        assert db.execute('SELECT state FROM cases WHERE id=?',(still_open,)).fetchone()[0]=='OPEN'
    assert retention.archive_terminal(store,90,apply=True)['eligible_cases']==0
    with pytest.raises(ValueError):
        retention.archive_terminal(store,0,apply=True)
