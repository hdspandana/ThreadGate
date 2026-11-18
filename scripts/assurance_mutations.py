"""Small, isolated negative checks; never edits the working tree or labels.

A baseline selected regression must pass before its one-line mutation is tested.
This is targeted safeguard sensitivity, not a whole-program mutation score.
"""
import json
import xml.etree.ElementTree as ET
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[1]
MUTATIONS=[
 ('source-binding','pipeline.py','hashlib.sha256(raw.encode()).hexdigest()',"''",'test_source_binding_includes_each_email_component'),
 ('reference-binding','pipeline.py','hashlib.sha256(json.dumps(vendor.data,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode()).hexdigest()',"''",'test_same_version_full_reference_content_change_invalidates_attestation'),
 ('account-letter-repair','compare.py',"return digits if digits.isascii() and digits.isdigit() else 'invalid:'+digits",r"return re.sub(r'\D','',digits)",'test_account_letters_are_not_silently_stripped'),
 ('audit-content-hash','audit_integrity.py','return hashlib.sha256(canonical.encode()).hexdigest()','return GENESIS','test_audit_row_link_head_and_truncation_are_detected'),
 ('missing-head-rebaseline','audit_integrity.py',"if not allow_legacy or db.execute('SELECT COUNT(*) FROM audit_chain').fetchone()[0]:",'if False:','test_schema3_missing_head_is_not_silently_rebaselined'),
 ('receipt-comparison','audit_integrity.py',"if receipt_digest(db,event_id)!=details['receipt_digest']:",'if False:','test_anchored_receipt_and_workflow_event_tampering_detected'),
 ('transaction-rollback','workspace.py','            db.rollback()','            db.commit()','test_receipt_state_event_and_chain_roll_back_together_on_audit_failure'),
]


EXPECTED={
 'source-binding':['first.verification.request_digest!=changed.verification.request_digest'],
 'reference-binding':['first.verification.reference_digest!=changed.verification.reference_digest'],
 'account-letter-repair':["normalize_value('account_number',value)!=normalize_value"],
 'audit-content-hash':['DID NOT RAISE','AuditIntegrityError'],
 'missing-head-rebaseline':['DID NOT RAISE','AuditIntegrityError'],
 'receipt-comparison':['DID NOT RAISE','AuditIntegrityError'],
 'transaction-rollback':["assert 'VERIFIED' == 'ASSIGNED'"],
}


def expected_failures(xml_path,test,markers):
    try:root=ET.parse(xml_path).getroot()
    except (OSError,ET.ParseError):return []
    failures=[]
    for case in root.iter('testcase'):
        if case.find('error') is not None or case.find('skipped') is not None:return []
        failure=case.find('failure')
        if failure is None:continue
        name=case.get('name','');text=(failure.get('message','')+' '+(failure.text or ''))
        if not (name==test or name.startswith(test+'[')) or not all(m in text for m in markers):return []
        failures.append(name)
    return failures


def main():
    rows=[];output=ROOT/'data/runs/assurance/mutations';output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='threadgate-mutations-') as folder:
        root=Path(folder)
        shutil.copytree(ROOT/'src',root/'src',ignore=shutil.ignore_patterns('__pycache__'))
        for name in ['cases','records']:shutil.copytree(ROOT/'data'/name,root/'data'/name)
        (root/'tests').mkdir();shutil.copy2(ROOT/'tests/test_engineering_assurance.py',root/'tests/test_engineering_assurance.py')
        (root/'pytest.ini').write_text('[pytest]\npythonpath = src\n')
        for name,file,old,new,test in MUTATIONS:
            target=root/'src/threadgate'/file;original=target.read_text()
            xml=root/'result.xml'
            command=[sys.executable,'-m','pytest','-q','--junitxml='+str(xml),'tests/test_engineering_assurance.py::'+test]
            baseline=subprocess.run(command,cwd=root,capture_output=True,text=True,timeout=90)
            if baseline.returncode!=0:raise RuntimeError('Mutation baseline failed: '+name)
            if original.count(old)!=1:raise RuntimeError('Mutation target is not unique: '+name)
            target.write_text(original.replace(old,new,1))
            try:mutant=subprocess.run(command,cwd=root,capture_output=True,text=True,timeout=90)
            finally:target.write_text(original)
            failures=expected_failures(xml,test,EXPECTED[name])
            killed=mutant.returncode==1 and bool(failures)
            (output/(name+'.txt')).write_text('BASELINE\n'+baseline.stdout+baseline.stderr+'\nMUTANT\n'+mutant.stdout+mutant.stderr)
            rows.append({'safeguard':name,'test':test,'baseline_exit':baseline.returncode,'mutant_exit':mutant.returncode,'killed':killed,'expected_failure_markers':EXPECTED[name],'matched_failed_tests':failures})
    report={'scope':'Seven targeted isolated one-line safeguard mutations, not full mutation coverage.',
            'attempted':len(rows),'killed':sum(r['killed'] for r in rows),'rows':rows}
    (output/'summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    return 0 if all(r['killed'] for r in rows) else 1


if __name__=='__main__':raise SystemExit(main())
