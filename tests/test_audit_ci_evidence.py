"""Reporting regressions use tiny synthetic XML and mocked commands, no installs/ZIPs."""
import importlib.util
import json
from pathlib import Path
import subprocess
from unittest.mock import patch
import pytest

ROOT = Path(__file__).resolve().parents[1]
SENTINEL = 'SYNTHETIC_PRIVATE_DIAGNOSTIC_MUST_NOT_BE_EMITTED'
XML = f'''<testsuites><testsuite tests="4"><testcase name="{SENTINEL}"/>
<testcase><failure>{SENTINEL}</failure></testcase>
<testcase><error>{SENTINEL}</error></testcase>
<testcase><skipped>{SENTINEL}</skipped></testcase></testsuite></testsuites>'''


@pytest.fixture
def tools(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'scripts'))
    import scripts.validation_evidence as validation_evidence
    monkeypatch.setattr(validation_evidence,'checkout_identity',lambda root:'a'*40)
    def load(name):
        spec=importlib.util.spec_from_file_location('audit_'+name,ROOT/'scripts'/f'{name}.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module
    return validation_evidence,load('ci_guard'),load('release_check')


def test_junit_counts_and_warning_availability(tools,tmp_path):
    evidence,_,_=tools
    xml=tmp_path/'tests.xml';xml.write_text(XML)
    counts=evidence.test_summary(xml,'1 failed, 1 passed, 1 skipped, 1 error, 2 warnings in 0.20s')
    assert counts==dict(status='AVAILABLE',total=4,passed=1,failures=1,errors=1,skips=1,warnings=2,history_skips=0)
    assert evidence.test_summary(xml)['warnings'] is None
    assert evidence.test_summary(xml,'1 passed in 0.20s')['warnings']==0
    assert evidence.test_summary(tmp_path/'absent')['status']=='UNAVAILABLE'
    xml.write_text('<incomplete')
    assert evidence.test_summary(xml)['total'] is None
    assert evidence.test_summary()['status']=='NOT RUN'


@pytest.mark.parametrize('value',[True,-1,'12',1.5])
def test_evidence_refuses_non_numeric_or_invalid_counts(tools,value):
    evidence,_,_=tools
    report=dict(phase='source',status='PASS',tests=dict(status='AVAILABLE',total=value,passed=1,failures=0,errors=0,skips=0,warnings=None))
    with pytest.raises(ValueError):evidence.sanitized(report)


def test_allowlist_removes_raw_fields_and_rejects_totals(tools,tmp_path):
    evidence,_,_=tools
    xml=tmp_path/'tests.xml';xml.write_text(XML)
    report=dict(phase='source',status='FAIL',tests=evidence.test_summary(xml),
                steps=[dict(step='tests',status='FAIL',exit_code=1,raw=SENTINEL)],raw=SENTINEL,python=SENTINEL)
    assert SENTINEL not in json.dumps(evidence.sanitized(report))
    report['tests']['total']=99
    with pytest.raises(ValueError):evidence.sanitized(report)


@pytest.mark.parametrize('phase',['source','fresh-extracted'])
@pytest.mark.parametrize('fault',[
    None,'missing','stale','malformed','inconsistent','unavailable','no-steps',
    'failed-step','duplicate-step','wrong-commit','wrong-invocation','wrong-workflow',
    'wrong-attempt','wrong-phase','wrong-format','phase-fail','failed-test','unapproved-skip','empty-tests',
])
def test_mandatory_wrapper_invariant(tools,tmp_path,monkeypatch,capsys,phase,fault):
    evidence,guard,_=tools
    monkeypatch.setattr(guard,'ROOT',tmp_path)
    monkeypatch.setenv('EXPECTED_SHA','a'*40)
    monkeypatch.setenv('GITHUB_ACTIONS','true')
    monkeypatch.setenv('GITHUB_RUN_ID','123')
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT','2')
    path=evidence.evidence_path(tmp_path,phase)
    path.parent.mkdir(parents=True)
    path.write_text('old evidence must not survive')
    other=evidence.evidence_path(tmp_path,'source' if phase=='fresh-extracted' else 'fresh-extracted')
    other.write_text('other phase retained')
    def fake(command,**kwargs):
        assert not path.exists(), 'Prior-run evidence was not invalidated'
        with patch.dict('os.environ',kwargs['env'],clear=True):
            report=evidence.write_evidence(tmp_path,phase,'PASS',
                dict(status='AVAILABLE',total=1,passed=1,failures=0,errors=0,skips=0,warnings=None,history_skips=0),
                [dict(step=s,status='PASS',exit_code=0) for s in evidence.PHASE_STEPS[phase]])
        if fault=='missing':path.unlink()
        elif fault=='malformed':path.write_text(SENTINEL+' not JSON')
        else:
            if fault=='stale':report['run_id']='b'*32
            elif fault=='wrong-invocation':report['run_id']=None
            elif fault=='inconsistent':report['tests']['total']=9
            elif fault=='unavailable':report['tests']=evidence.test_summary()
            elif fault=='no-steps':report['steps']=[]
            elif fault=='failed-step':report['steps'][0]['status']='FAIL'
            elif fault=='duplicate-step':report['steps'].append(report['steps'][0])
            elif fault=='wrong-commit':report['source_commit']='b'*40  # expected_sha still correct
            elif fault=='wrong-workflow':report['workflow_run_id']='999'
            elif fault=='wrong-attempt':report['workflow_attempt']='1'
            elif fault=='wrong-phase':report['phase']='source' if phase!='source' else 'fresh-extracted'
            elif fault=='wrong-format':report['format']='old-format'
            elif fault=='phase-fail':report['status']='FAIL'
            elif fault=='failed-test':report['tests'].update(total=2,failures=1)
            elif fault=='unapproved-skip':report['tests'].update(total=2,skips=1)
            elif fault=='empty-tests':report['tests'].update(total=0,passed=0)
            report['raw']=SENTINEL
            path.write_text(json.dumps(report))
        return subprocess.CompletedProcess(command,0)  # EVERY fault has a zero child exit.
    monkeypatch.setattr(guard.subprocess,'run',fake)
    command=['python','scripts/release_check.py','--require-history'] if phase=='source' else ['python','scripts/ci_guard.py','fresh']
    code=guard.run(command)
    assert code==(0 if fault is None else 1)
    output=capsys.readouterr().out
    assert SENTINEL not in output and phase in output
    assert other.read_text()=='other phase retained'
    if fault is None:
        report=json.loads(output.split('CI evidence: ')[1])
        assert report['tests']['passed']==1 and report['tests']['warnings'] is None
    else:assert 'CI evidence FAIL:' in output


def test_optional_diagnostic_requires_no_test_evidence(tools,monkeypatch):
    _,guard,_=tools
    monkeypatch.setattr(guard.subprocess,'run',lambda *a,**k:subprocess.CompletedProcess(a,0))
    assert guard.run(['python','-c','pass'])==0


def test_source_gate_keeps_twelve_steps_and_records_counts(tools,tmp_path,monkeypatch):
    evidence,_,gate=tools
    assert tuple(name for name,_ in gate.commands())==evidence.PHASE_STEPS['source']
    monkeypatch.setattr(gate,'ROOT',tmp_path)
    seen=[]
    def fake(command,**kwargs):
        seen.append(command)
        output=SENTINEL
        if '--junitxml' in command:
            Path(command[command.index('--junitxml')+1]).write_text('<testsuite><testcase/></testsuite>')
            output+='\n1 passed, 2 warnings in 0.01s\n'
        return subprocess.CompletedProcess(command,0,output,'')
    monkeypatch.setattr(gate.subprocess,'run',fake)
    assert gate.main([])==0
    assert len(seen)==12
    report=json.loads((tmp_path/'data/runs/ci-evidence/source.json').read_text())
    assert report['status']=='PASS' and report['tests']['passed']==1 and report['tests']['warnings']==2
    assert SENTINEL not in json.dumps(report)
    assert not list(tmp_path.rglob('*.zip'))


@pytest.mark.parametrize('failed_step',[None,'install','tests','kill_gate.py'])
def test_fresh_reporting_with_mocked_extraction_and_commands(tools,tmp_path,monkeypatch,capsys,failed_step):
    evidence,guard,_=tools
    monkeypatch.setattr(guard,'ROOT',tmp_path)
    monkeypatch.setattr(guard,'capacity',lambda minimum:None)
    monkeypatch.setenv('RUNNER_TEMP',str(tmp_path))
    monkeypatch.setenv('EXPECTED_SHA','a'*40)
    release=tmp_path/'release';release.mkdir()
    (release/'TeamWorkspace-manifest.json').write_text(json.dumps({'source_identity':{'source_commit':'a'*40}}))
    seen=[]
    def fake(command,**kwargs):
        seen.append(command)
        is_tests='pytest' in command
        fails=(failed_step=='install' and 'install' in command or failed_step=='tests' and is_tests
               or failed_step=='kill_gate.py' and any(Path(arg).name=='kill_gate.py' for arg in command))
        if is_tests:
            Path(command[command.index('--junitxml')+1]).write_text(
                '<testsuite><testcase><failure/></testcase></testsuite>' if fails else '<testsuite><testcase/></testsuite>')
        return subprocess.CompletedProcess(command,int(bool(fails)),SENTINEL+'\n1 passed in 0.01s\n','')
    monkeypatch.setattr(guard.subprocess,'run',fake)
    # No archive exists: the extraction boundary is explicitly mocked.
    with patch('zipfile.ZipFile') as archive:
        if failed_step:
            with pytest.raises(subprocess.CalledProcessError):guard.fresh()
        else:
            guard.fresh()
        archive.return_value.__enter__.return_value.extractall.assert_called_once()
    report=json.loads((tmp_path/'data/runs/ci-evidence/fresh-extracted.json').read_text())
    assert report['status']==('FAIL' if failed_step else 'PASS')
    assert report['tests']['status']==('NOT RUN' if failed_step=='install' else 'AVAILABLE')
    if failed_step=='tests':assert report['tests']['failures']==1
    if failed_step=='kill_gate.py':assert report['tests']['passed']==1
    assert len(seen)==(3 if failed_step=='install' else 4 if failed_step=='tests' else 5 if failed_step else 6)
    assert SENTINEL not in json.dumps(report) and SENTINEL not in capsys.readouterr().out
    assert not list(tmp_path.rglob('*.zip'))


@pytest.mark.parametrize('before_tests',[True,False])
def test_source_early_failure_does_not_reuse_old_xml(tools,tmp_path,monkeypatch,before_tests):
    _,_,gate=tools
    monkeypatch.setattr(gate,'ROOT',tmp_path)
    folder=tmp_path/'data/runs/release-check';folder.mkdir(parents=True)
    (folder/'tests.xml').write_text('<testsuite><testcase/></testsuite>')
    def fake(command,**kwargs):
        fail=before_tests or '--junitxml' in command
        return subprocess.CompletedProcess(command,int(fail),'SYNTHETIC startup failure','')
    monkeypatch.setattr(gate.subprocess,'run',fake)
    assert gate.main([])==1
    report=json.loads((tmp_path/'data/runs/ci-evidence/source.json').read_text())
    assert report['status']=='FAIL'
    assert report['tests']['status']==('NOT RUN' if before_tests else 'UNAVAILABLE')
    assert report['tests']['total'] is None


def test_actual_checkout_observation_not_expected_sha(tools,monkeypatch):
    evidence,_,_=tools
    # Restore the actual implementation rather than the test fixture's observation mock.
    namespace={}
    import ast
    node=next(n for n in ast.parse((ROOT/'scripts/validation_evidence.py').read_text()).body
              if isinstance(n,ast.FunctionDef) and n.name=='checkout_identity')
    namespace.update(subprocess=subprocess,re=__import__('re'),Path=Path)
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual-checkout-observer>','exec'),namespace)
    with patch.object(subprocess,'check_output',side_effect=[str(ROOT),'a'*40+'\n','']):
        assert namespace['checkout_identity'](ROOT)=='a'*40
    with patch.object(subprocess,'check_output',side_effect=[str(ROOT),'a'*40+'\n',' M app/product.py']):
        assert namespace['checkout_identity'](ROOT) is None
    with patch.object(subprocess,'check_output',return_value=str(ROOT.parent)):
        assert namespace['checkout_identity'](ROOT) is None
    monkeypatch.setenv('EXPECTED_SHA','b'*40)
    with pytest.raises(ValueError):evidence.invocation(ROOT,'c'*32)


def test_checkout_change_during_successful_command_fails(tools,tmp_path,monkeypatch):
    evidence,guard,_=tools
    monkeypatch.setattr(guard,'ROOT',tmp_path)
    monkeypatch.setenv('EXPECTED_SHA','a'*40)
    observations=iter(['a'*40,'b'*40])
    monkeypatch.setattr(evidence,'checkout_identity',lambda root:next(observations))
    monkeypatch.setattr(guard.subprocess,'run',lambda *a,**k:subprocess.CompletedProcess(a,0))
    assert guard.run(['python','scripts/release_check.py','--require-history'])==1


@pytest.mark.parametrize('phase',['source','fresh-extracted'])
def test_only_documented_export_history_skip_is_acceptable(tools,phase):
    evidence,_,_=tools
    counts=dict(status='AVAILABLE',total=2,passed=1,failures=0,errors=0,skips=1,warnings=None,history_skips=1)
    if phase=='source':
        with pytest.raises(ValueError):evidence.validate_test_outcomes(counts,phase)
    else:evidence.validate_test_outcomes(counts,phase)
    counts['history_skips']=0
    with pytest.raises(ValueError):evidence.validate_test_outcomes(counts,phase)


def test_inconsistent_junit_header_is_unavailable(tools,tmp_path):
    evidence,_,_=tools
    xml=tmp_path/'counts.xml';xml.write_text('<testsuite tests="10"><testcase/></testsuite>')
    assert evidence.test_summary(xml)['status']=='UNAVAILABLE'


def test_workflow_upload_requires_all_verifications():
    # Restricted assertions over the project's actual simple job structure; no new YAML dependency.
    text=(ROOT/'.github/workflows/verify.yml').read_text()
    job=text.split('  offline-verification:\n',1)[1].split('  container-smoke:\n',1)[0]
    assert 'needs: [container-smoke, browser-regression]' in job
    lines=job.splitlines()
    upload=next(i for i,line in enumerate(lines) if 'uses: actions/upload-artifact@' in line)
    required=['scripts/ci_guard.py run python scripts/release_check.py --require-history',
              'scripts/ci_guard.py run python scripts/verify_release.py --require-commit',
              'scripts/ci_guard.py run python scripts/ci_guard.py fresh']
    indexes=[next(i for i,line in enumerate(lines) if command in line) for command in required]
    assert indexes==sorted(indexes) and all(i<upload for i in indexes)
    assert all(lines[i].startswith('      - run: ') for i in indexes)
    assert 'continue-on-error' not in job
    conditions=[line.strip() for line in lines if line.strip().startswith('if:')]
    assert conditions==["if: success() && vars.THREADGATE_ARTIFACT_UPLOAD_APPROVED == 'true'"]
    assert 'if: success()' in lines[upload+1]


def test_fresh_zero_exit_without_junit_fails_before_later_commands(tools,tmp_path,monkeypatch):
    evidence,guard,_=tools
    monkeypatch.setattr(guard,'ROOT',tmp_path)
    monkeypatch.setattr(guard,'capacity',lambda minimum:None)
    monkeypatch.setenv('EXPECTED_SHA','a'*40)
    monkeypatch.setenv('RUNNER_TEMP',str(tmp_path))
    folder=tmp_path/'release';folder.mkdir()
    (folder/'TeamWorkspace-manifest.json').write_text(json.dumps({'source_identity':{'source_commit':'a'*40}}))
    seen=[]
    def fake(command,**kwargs):
        seen.append(command)
        return subprocess.CompletedProcess(command,0,SENTINEL,'')
    monkeypatch.setattr(guard.subprocess,'run',fake)
    with patch('zipfile.ZipFile'):
        with pytest.raises(ValueError):guard.fresh()
    assert len(seen)==4 and 'pytest' in seen[-1]
    report=json.loads(evidence.evidence_path(tmp_path,'fresh-extracted').read_text())
    assert report['status']=='FAIL' and report['tests']['status']=='UNAVAILABLE'
    assert report['steps'][-1]==dict(step='tests',status='FAIL',exit_code=0)


def test_fresh_history_skip_is_recognized_without_publishing_name(tools,tmp_path):
    evidence,_,_=tools
    xml=tmp_path/'history.xml'
    xml.write_text('<testsuite tests="2"><testcase/>'+f'<testcase classname="tests.test_reproducibility_and_failure_paths" name="{evidence.HISTORY_TEST}">'+
        '<skipped message="not a clone - the full-history claim cannot be checked here"/></testcase></testsuite>')
    counts=evidence.test_summary(xml)
    assert counts['skips']==counts['history_skips']==1
    evidence.validate_test_outcomes(counts,'fresh-extracted')
    assert evidence.HISTORY_TEST not in json.dumps(counts)
