"""Content binding, normalization, audit/receipt tampering and rollback regressions.

Synthetic-only; no provider call. Ground-truth corpus labels are not modified.
"""
import copy
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
import uuid
import pytest
from threadgate import audit_integrity
from threadgate.attestation import AttestationStore,VerificationEvent
from threadgate.clock import fixed
from threadgate.compare import normalize_value
from threadgate.pipeline import run_case
from threadgate.presentation import comparison_html,masked_text
from threadgate.provider_observation import capture,observe,error_kind
from threadgate.records import load_vendors,load_cases
from threadgate.workspace import Workspace

ROOT=Path(__file__).resolve().parents[1]
VENDORS=load_vendors(ROOT/'data/records/vendor_master.json')
CASE=load_cases(ROOT/'data/cases/frozen_v1.json')[0]
PASSWORD='synthetic-assurance-only-passphrase'


def investigate(case=None,vendors=None,**kwargs):
    return run_case(copy.deepcopy(case or CASE),vendors or VENDORS,
                    extractor_mode='offline',clock=fixed('2026-10-06'),**kwargs)


def event_for(context,actor='verifier',**changes):
    event=VerificationEvent(str(uuid.uuid4()),context.vendor_id,context.request_id,
        context.destination_digest,context.reference_version,actor,'2026-10-06T00:00:00Z',
        request_digest=context.request_digest,reference_digest=context.reference_digest)
    return replace(event,**changes)


@pytest.fixture
def team(tmp_path):
    service=Workspace(tmp_path/'assurance.db',clock=lambda:1000000)
    service.bootstrap('owner',PASSWORD)
    tokens={'admin':service.login('owner',PASSWORD)}
    for role in ['analyst','verifier','auditor']:
        service.create_user(tokens['admin'],role,PASSWORD,role)
        tokens[role]=service.login(role,PASSWORD)
    result=investigate()
    case_id=service.submit(tokens['analyst'],result)
    service.assign(tokens['analyst'],case_id,'verifier',1)
    return service,tokens,result,case_id


def attest(team):
    service,tokens,result,case_id=team
    event=event_for(result.verification)
    outcome=service.verify(tokens['verifier'],case_id,2,event,result.verification,True,True,True)
    assert outcome.accepted
    return event


def test_ad_hoc_request_id_is_stable_and_changes_with_source():
    case=copy.deepcopy(CASE);case.pop('id',None)
    first=investigate(case);second=investigate(case)
    assert first.case_id==second.case_id and first.verification.request_digest
    case['email']['body']+='\nDo not rely on an earlier callback.'
    changed=investigate(case)
    assert changed.case_id!=first.case_id
    assert changed.verification.request_digest!=first.verification.request_digest


@pytest.mark.parametrize('field',['body','subject','from','reply_to','received_at'])
def test_source_binding_includes_each_email_component(field):
    first=investigate();case=copy.deepcopy(CASE)
    case['email'][field]=case['email'].get(field,'')+' synthetic changed source'
    changed=investigate(case)
    assert first.verification.request_id==changed.verification.request_id
    assert first.verification.request_digest!=changed.verification.request_digest
    outcome=AttestationStore().consume(event_for(first.verification),changed.verification)
    assert not outcome.accepted and outcome.consumed


@pytest.mark.parametrize('part',['contact','verified_domains','alternate'])
def test_same_version_full_reference_content_change_invalidates_attestation(part):
    vendors=copy.deepcopy(VENDORS);vendor=vendors[CASE['vendor_id']]
    if part=='contact':vendor.data['verified_contacts']['contact_phone']='+91-80000-00999'
    elif part=='verified_domains':vendor.data['verified_domains'].append('new.synthetic.example')
    else:vendor.data['allowlisted_accounts'].append({'account_number':'777888999000'})
    first=investigate();changed=investigate(vendors=vendors)
    assert first.verification.reference_version==changed.verification.reference_version
    assert first.verification.reference_digest!=changed.verification.reference_digest
    outcome=AttestationStore().consume(event_for(first.verification),changed.verification)
    assert not outcome.accepted and outcome.consumed


def test_unknown_vendor_is_hold_even_if_model_suppresses_change():
    case={'email':{'body':'Nothing has changed.'},'vendor_id':'UNKNOWN-SYNTHETIC'}
    result=run_case(case,VENDORS,extractor_mode='compromised',clock=fixed('2026-10-06'))
    assert result.decision.decision=='HOLD' and result.decision.attestation_required
    assert any(f.code=='R_VENDOR_UNAVAILABLE' and f.independent_of_model for f in result.decision.findings)


@pytest.mark.parametrize('email',[None,[],{'body':None},{'body':123},{'body':'x'*22001},{'body':'test','subject':['invalid']}])
def test_malformed_or_oversize_input_never_reaches_extractor(email):
    def forbidden(*args,**kwargs):pytest.fail('Extractor reached for rejected input')
    with pytest.raises(ValueError):run_case({'email':email,'vendor_id':'V-1001'},VENDORS,extractor_fn=forbidden)


def test_provider_failure_does_not_expose_exception_text():
    def failing(*args,**kwargs):raise TimeoutError('PRIVATE-SOURCE-AND-SECRET-MUST-NOT-LEAK')
    result=investigate(extractor_fn=failing)
    assert result.decision.decision=='HOLD'
    assert result.error_kind=='timeout'
    assert 'PRIVATE' not in result.error and 'SECRET' not in result.error


@pytest.mark.parametrize('value',['501002A34554455','501002А34554455','50100234554455evil','A50100234554455'])
def test_account_letters_are_not_silently_stripped(value):
    assert normalize_value('account_number',value)!=normalize_value('account_number','50100234554455')


@pytest.mark.parametrize('value',['50100 23455 4455','50100-23455-4455','５０１００２３４５５４４５５'])
def test_permitted_account_presentation_separators_remain_equivalent(value):
    assert normalize_value('account_number',value)=='50100234554455'


@pytest.mark.parametrize('mode',['offline','compromised','compromised_quote'])
def test_explicit_malformed_account_is_independently_held(mode):
    case={'vendor_id':'V-1001','email':{'body':'Update account number: 501002A34554455.'}}
    result=run_case(case,VENDORS,extractor_mode=mode,clock=fixed('2026-10-06'))
    assert result.decision.decision=='HOLD'
    assert any(f.code=='I_MALFORMED_ACCOUNT' and f.independent_of_model for f in result.decision.findings)


@pytest.mark.parametrize('sql',[
    "UPDATE audit SET actor='forged' WHERE seq=(SELECT MIN(seq) FROM audit)",
    "UPDATE audit_chain SET previous_hash='forged' WHERE seq=(SELECT MAX(seq) FROM audit_chain)",
    "DELETE FROM audit_chain WHERE seq=(SELECT MAX(seq) FROM audit_chain)",
    "DELETE FROM audit WHERE seq=(SELECT MAX(seq) FROM audit)",
    "UPDATE audit_head SET hash='forged' WHERE id=1",
])
def test_audit_row_link_head_and_truncation_are_detected(team,sql):
    service,tokens,_,_=team
    assert service.audit_integrity(tokens['auditor'])['status']=='PASS'
    # Simulate out-of-band database corruption; FK disabling is deliberate.
    with sqlite3.connect(service.path) as db:db.execute(sql)
    with pytest.raises(audit_integrity.AuditIntegrityError):service.audit(tokens['auditor'])


def test_schema3_missing_head_is_not_silently_rebaselined(team):
    service,_,_,_=team
    with sqlite3.connect(service.path) as db:
        db.execute('DELETE FROM audit_chain');db.execute('DELETE FROM audit');db.execute('DELETE FROM audit_head')
    with pytest.raises(audit_integrity.AuditIntegrityError):Workspace(service.path)


@pytest.mark.parametrize('sql',[
    "UPDATE verification_receipts SET reference_digest='forged'",
    "UPDATE verification_receipts SET assigned_verifier='forged'",
    "DELETE FROM verification_receipts",
    "UPDATE workflow_events SET outcome='forged'",
    "DELETE FROM workflow_events",
])
def test_anchored_receipt_and_workflow_event_tampering_detected(team,sql):
    service,tokens,_,case_id=team;attest(team)
    assert service.export_case(tokens['auditor'],case_id)['audit_integrity']['status']=='PASS'
    with sqlite3.connect(service.path) as db:db.execute(sql)
    with pytest.raises(audit_integrity.AuditIntegrityError):service.audit_integrity(tokens['auditor'])
    with pytest.raises(audit_integrity.AuditIntegrityError):service.export_case(tokens['auditor'],case_id)


def test_receipt_state_event_and_chain_roll_back_together_on_audit_failure(team,monkeypatch):
    service,tokens,result,case_id=team
    before=service.audit_integrity(tokens['auditor'])
    event=event_for(result.verification)
    def fail(*args,**kwargs):raise RuntimeError('synthetic fault before audit append')
    with monkeypatch.context() as patch:
        patch.setattr(audit_integrity,'append',fail)
        with pytest.raises(RuntimeError):service.verify(tokens['verifier'],case_id,2,event,result.verification,True,True,True)
    assert service.get_case(tokens['auditor'],case_id)['state']=='ASSIGNED'
    with service._db() as db:
        assert db.execute('SELECT COUNT(*) FROM verification_receipts').fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM workflow_events').fetchone()[0]==0
    assert service.audit_integrity(tokens['auditor'])==before
    # Event was not consumed in a rolled-back transaction and can be retried.
    assert service.verify(tokens['verifier'],case_id,2,event,result.verification,True,True,True).accepted


def test_schema2_migration_trusts_history_once_and_is_idempotent(tmp_path):
    path=tmp_path/'legacy.db'
    service=Workspace(path);service.bootstrap('owner',PASSWORD)
    with sqlite3.connect(path) as db:
        for table in ['verification_receipts','audit_head','audit_chain']:db.execute('DROP TABLE '+table)
        db.execute('PRAGMA user_version=2')
        count=db.execute('SELECT COUNT(*) FROM audit').fetchone()[0]
    migrated=Workspace(path)
    with migrated._db() as db:
        report=audit_integrity.verify_all(db);assert report['events']==count
        assert db.execute('PRAGMA user_version').fetchone()[0]==3
    with Workspace(path)._db() as db:assert audit_integrity.verify_all(db)==report


def test_migration_failure_rolls_back_version_and_chain_and_can_retry(tmp_path,monkeypatch):
    path=tmp_path/'migration.db';service=Workspace(path);service.bootstrap('owner',PASSWORD)
    with sqlite3.connect(path) as db:
        for table in ['verification_receipts','audit_head','audit_chain']:db.execute('DROP TABLE '+table)
        db.execute('PRAGMA user_version=2')
    def fail(*args):raise RuntimeError('synthetic migration failure')
    with monkeypatch.context() as patch:
        patch.setattr(audit_integrity,'event_digest',fail)
        with pytest.raises(RuntimeError):Workspace(path)
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==2
        assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE name='audit_chain'").fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM audit').fetchone()[0]>0
    with Workspace(path)._db() as db:assert audit_integrity.verify_all(db)['status']=='PASS'


def test_concurrent_open_and_append_remain_consistent(team):
    service,tokens,result,_=team
    def create(i):
        opened=Workspace(service.path,clock=lambda:1000000)
        return opened.submit(tokens['analyst'],result,title='Synthetic request '+str(i))
    with ThreadPoolExecutor(max_workers=4) as workers:ids=list(workers.map(create,range(8)))
    assert len(set(ids))==8
    assert service.audit_integrity(tokens['auditor'])['status']=='PASS'


def test_readonly_cli_checks_receipts_and_does_not_change_store(team):
    service,_,_,_=team;attest(team)
    before=Path(service.path).read_bytes()
    proc=subprocess.run([sys.executable,str(ROOT/'scripts/verify_audit.py'),'--db',service.path],capture_output=True,text=True)
    assert proc.returncode==0 and json.loads(proc.stdout)['status']=='PASS'
    assert Path(service.path).read_bytes()==before
    with sqlite3.connect(service.path) as db:db.execute("UPDATE verification_receipts SET analyst='forged'")
    proc=subprocess.run([sys.executable,str(ROOT/'scripts/verify_audit.py'),'--db',service.path],capture_output=True,text=True)
    assert proc.returncode==1 and json.loads(proc.stdout)['status']=='FAIL'


def test_masked_comparison_has_semantic_labels_and_safe_reveal():
    result=investigate()
    masked=comparison_html(result)
    assert '50100234559821' not in masked and '••••' in masked
    assert 'Trusted record' in masked and 'Requested' in masked and 'scope="col"' in masked
    revealed=comparison_html(result,True)
    assert '501002' in revealed and '<mark>' in revealed and '<del>' in revealed
    result.decision.diffs[0].new_value='<script>alert(1)</script>'
    assert '<script>' not in comparison_html(result,True)


@pytest.mark.parametrize('text',['Account number: 50100234559821','Confirm that 50100234559821 belongs to the vendor.',
    'Account number: 501002A34554455','Pay ５０１００２３４５５９８２１','Reply to receipts@synthetic.example'])
def test_masked_text_covers_supported_identifiers_and_source_quotes(text):
    assert text!=masked_text(text)
    assert '50100234559821' not in masked_text(text)


def test_provider_observation_is_request_local_and_does_not_collect_content():
    def run(i):
        with capture() as events:
            observe(i,'response',4,response=SimpleNamespace(usage_metadata=SimpleNamespace(total_token_count=42),text='PRIVATE'))
        return events
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(run,range(8)))
    assert all(len(events)==1 and events[0]['attempt']==i for i,events in enumerate(results))
    assert 'PRIVATE' not in json.dumps(results)
    with capture() as events:assert events==[]


@pytest.mark.parametrize(
    'code,kind',
    [
        (400, 'client_error'),
        (429, 'rate_limit'),
        (401, 'authentication'),
        (403, 'authentication'),
        (500, 'provider'),
    ],
)
def test_provider_error_classification_does_not_swallow_status(code,kind):
    exc=RuntimeError('PRIVATE');exc.code=code
    assert error_kind(exc)==kind


def test_frozen_corpus_is_distinct_and_heldout_remains_reserved():
    spec=importlib.util.spec_from_file_location('assurance_eval',ROOT/'eval/assurance_eval.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    development,manifest=module.verified_corpus(False)
    heldout=json.loads((ROOT/'data/assurance/heldout.json').read_text())['cases']
    assert len({c['category'] for c in development})>=13 and len(heldout)>=13
    assert not ({json.dumps(c['email'],sort_keys=True) for c in development}&{json.dumps(c['email'],sort_keys=True) for c in heldout})
    assert module.main(['--include-heldout'])==2
    assert manifest['prompt_tuning_on_heldout'] is False


def test_metric_denominators_are_explicit_and_zero_samples_are_not_perfect():
    spec=importlib.util.spec_from_file_location('assurance_eval',ROOT/'eval/assurance_eval.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert module.rate(0,0)=={'count':0,'sample_size':0,'rate':None}
    cases=[{'expected_decision':'HOLD','change_requested':True},{'expected_decision':'CLEAR','change_requested':False}]
    metrics=module.gate_metrics(cases,['CLEAR','HOLD'])
    assert metrics['false_CLEAR']==module.rate(1,1)
    assert metrics['false_HOLD']==module.rate(1,1)
    assert metrics['change_gate_false_negative_rate']==module.rate(1,1)
