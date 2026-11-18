"""Isolated synthetic backup/restore/retention exercise. No production data.

Temporary databases and credentials are destroyed. Optional --browser opens the
actual product on a restored store. Reports contain assertions, never credentials.
"""
import argparse
from datetime import datetime,timezone
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
import pyotp
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from threadgate.attestation import VerificationEvent
from threadgate.clock import fixed
from threadgate.pipeline import run_case
from threadgate.records import load_cases,load_vendors
from threadgate.workspace import Workspace,AccessDenied,Conflict


def restored_browser(db_path,password,expected_id,temp):
    from playwright.sync_api import sync_playwright
    with socket.socket() as sock:sock.bind(('0.0.0.0',0));port=sock.getsockname()[1]
    env=dict(os.environ)
    for key in ['GEMINI_API_KEY','GOOGLE_API_KEY']:env.pop(key,None)
    env.update(THREADGATE_SKIP_DOTENV='1',THREADGATE_REQUIRE_MFA='0',THREADGATE_WORKSPACE_DB=str(db_path))
    with (temp/'server.txt').open('w') as log:
        process=subprocess.Popen([sys.executable,'-m','streamlit','run',str(ROOT/'app/product.py'),
            '--server.address','0.0.0.0','--server.port',str(port),'--browser.gatherUsageStats','false'],
            cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
        try:
            deadline=time.monotonic()+40
            while time.monotonic()<deadline:
                if process.poll() is not None:raise RuntimeError('Restored app exited')
                try:urllib.request.urlopen(f'http://127.0.0.1:{port}/_stcore/health',timeout=1).close();break
                except OSError:time.sleep(.2)
            else:raise RuntimeError('Restored app readiness failed')
            with sync_playwright() as p:
                browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
                context=browser.new_context()
                context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(f'http://127.0.0.1:{port}/') else r.abort())
                page=context.new_page();page.set_default_timeout(20000);page.goto(f'http://127.0.0.1:{port}')
                page.get_by_label('Username',exact=True).fill('restore-auditor')
                page.get_by_label('Password',exact=True).fill(password)
                page.get_by_role('button',name='Sign in',exact=True).click()
                button=page.get_by_role('button',name='Export verification and audit bundle',exact=True)
                button.wait_for()
                with page.expect_download() as download:button.click()
                bundle=json.loads(Path(download.value.path()).read_text())
                assert bundle['case']['id']==expected_id and bundle['case']['state']=='VERIFIED'
                assert bundle['report']['gate_decision']=='HOLD' and bundle['audit_integrity']['status']=='PASS'
                assert page.get_by_test_id('stException').count()==0
                browser.close()
        finally:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)


def exercise(browser=False):
    checks=[]
    def check(identifier,condition,expected='PASS'):
        checks.append({'id':identifier,'expected':expected,'actual':'PASS' if condition else 'FAIL','status':'PASS' if condition else 'FAIL'})
        if not condition:raise AssertionError(identifier)
    with tempfile.TemporaryDirectory(prefix='threadgate-recovery-') as folder:
        temp=Path(folder);now=[time.time()];password=secrets.token_urlsafe(32)
        source=Workspace(temp/'source.db',clock=lambda:now[0],require_mfa=False)
        source.bootstrap('restore-owner',password);admin=source.login('restore-owner',password)
        tokens={}
        for role in ['analyst','verifier','auditor']:
            source.create_user(admin,'restore-'+role,password,role)
            tokens[role]=source.login('restore-'+role,password)
        seed=source.begin_mfa(tokens['verifier'],password)
        source.confirm_mfa(tokens['verifier'],pyotp.TOTP(seed).at(now[0]))
        now[0]+=31
        tokens['verifier']=source.login('restore-verifier',password,pyotp.TOTP(seed).at(now[0]))
        source.begin_mfa(admin,password)  # Pending enrollment must not revive on restore.
        case=load_cases(ROOT/'data/cases/frozen_v1.json')[0]
        result=run_case(case,load_vendors(ROOT/'data/records/vendor_master.json'),extractor_mode='offline',clock=fixed('2026-10-06'))
        key=str(uuid.uuid4());case_id=source.submit(tokens['analyst'],result,submission_key=key)
        source.assign(tokens['analyst'],case_id,'restore-verifier',1)
        c=result.verification
        event=VerificationEvent(str(uuid.uuid4()),c.vendor_id,c.request_id,c.destination_digest,c.reference_version,
            'restore-verifier',datetime.now(timezone.utc).isoformat(),request_digest=c.request_digest,reference_digest=c.reference_digest)
        check('source_authenticated_attestation',source.verify(tokens['verifier'],case_id,2,event,c,True,True,True).accepted)
        source_integrity=source.audit_integrity(tokens['auditor'])
        backup=temp/'private.backup'
        env=dict(os.environ);env['THREADGATE_SKIP_DOTENV']='1'
        for name in ['GEMINI_API_KEY','GOOGLE_API_KEY']:env.pop(name,None)
        proc=subprocess.run([sys.executable,str(ROOT/'scripts/backup_workspace.py'),'--db',source.path,'--output',str(backup)],
                            env=env,capture_output=True,text=True,timeout=30)
        check('online_backup_command',proc.returncode==0 and backup.is_file())
        if os.name=='posix':check('backup_private_mode',backup.stat().st_mode&0o777==0o600)
        # Simulate offline restore only; never overwrite source or use a live DB.
        restored_path=temp/'restored.db';shutil.copy2(backup,restored_path)
        restored=Workspace(restored_path,clock=lambda:now[0],require_mfa=False)
        with restored._db() as db:
            check('sqlite_integrity',db.execute('PRAGMA integrity_check').fetchone()[0]=='ok')
            check('historical_sessions_removed',db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]==0)
            check('pending_mfa_removed',db.execute("SELECT COUNT(*) FROM user_mfa WHERE pending<>''").fetchone()[0]==0)
            check('consumed_event_preserved',db.execute('SELECT COUNT(*) FROM workflow_events WHERE event_id=?',(event.event_id,)).fetchone()[0]==1)
        try:restored.principal(tokens['auditor']);revoked=False
        except AccessDenied:revoked=True
        check('prebackup_session_denied',revoked)
        auditor=restored.login('restore-auditor',password)
        check('restored_login_and_case',restored.get_case(auditor,case_id)['state']=='VERIFIED')
        current=restored.audit_integrity(auditor)
        check('restored_chain_and_receipts',current['status']=='PASS' and current['head_seq']>=source_integrity['head_seq'])
        proc=subprocess.run([sys.executable,str(ROOT/'scripts/verify_audit.py'),'--db',str(restored_path)],capture_output=True,text=True,timeout=30)
        check('readonly_composite_audit_cli',proc.returncode==0 and json.loads(proc.stdout)['status']=='PASS')
        now[0]+=31
        try:restored.login('restore-verifier',password);mfa_denied=False
        except AccessDenied:mfa_denied=True
        check('restored_mfa_still_required',mfa_denied)
        verifier=restored.login('restore-verifier',password,pyotp.TOTP(seed).at(now[0]))
        analyst=restored.login('restore-analyst',password)
        check('restored_submission_key',restored.submit(analyst,result,submission_key=key)==case_id)
        if browser:
            restored_browser(restored_path,password,case_id,temp)
            check('restored_product_browser_login_and_bundle',True)
        second=restored.submit(analyst,result,title='Synthetic replay attempt')
        restored.assign(analyst,second,'restore-verifier',1)
        try:restored.verify(verifier,second,2,event,c,True,True,True);denied=False
        except Conflict:denied=True
        check('restored_event_cannot_replay_on_new_case',denied)
        # Exercise approved local retention only after the restored workflow works.
        spec=importlib.util.spec_from_file_location('recovery_retention',ROOT/'scripts/retention.py')
        retention=importlib.util.module_from_spec(spec);spec.loader.exec_module(retention)
        now[0]+=120*86400
        dry=retention.archive_terminal(restored,90,False)
        check('retention_dry_run',dry['eligible_cases']==1)
        applied=retention.archive_terminal(restored,90,True)
        check('retention_applied',applied['eligible_cases']==1)
        auditor=restored.login('restore-auditor',password)
        bundle=restored.export_case(auditor,case_id)
        check('retained_gate_and_archive_state',bundle['case']['state']=='ARCHIVED' and bundle['report']['gate_decision']=='HOLD')
        check('retention_keeps_receipt_integrity',restored.audit_integrity(auditor)['status']=='PASS')
        with restored._db() as db:
            check('retention_keeps_replay_tombstone',db.execute('SELECT COUNT(*) FROM workflow_events WHERE event_id=?',(event.event_id,)).fetchone()[0]==1)
    return {'status':'PASS','scope':'Isolated synthetic online backup, offline restore, MFA/session/replay, receipt integrity and retention',
            'browser':'PASS' if browser else 'NOT RUN','provider_calls':0,'private_files_retained':False,
            'limitations':['Local temporary restore, not a host disaster-recovery exercise.','Rollback restores historical replay state; external reconciliation remains necessary.'],
            'checks':checks}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser',action='store_true')
    parser.add_argument('--output',default=str(ROOT/'data/runs/recovery-check.json'))
    args=parser.parse_args(argv)
    try:report=exercise(args.browser)
    except Exception as exc:
        report={'status':'FAIL','error_type':type(exc).__name__,'message':'Isolated recovery exercise failed; no successful recovery claimed.'}
    target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
