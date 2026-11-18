"""Protocol regressions. All provider artifacts below are explicitly simulated.

No heldout case is interpreted here, and no real provider is called.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
from concurrent.futures import ThreadPoolExecutor
import pytest

ROOT=Path(__file__).resolve().parents[1]


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


@pytest.fixture
def evaluator(tmp_path,monkeypatch):
    module=load('workflow_eval',ROOT/'eval/assurance_eval.py')
    root=tmp_path/'isolated';root.mkdir()
    for folder in ['src/threadgate','data/assurance','data/records']:
        shutil.copytree(ROOT/folder,root/folder,ignore=shutil.ignore_patterns('__pycache__'))
    (root/'eval').mkdir();shutil.copy2(ROOT/'eval/assurance_eval.py',root/'eval/assurance_eval.py')
    shutil.copy2(ROOT/'requirements.lock',root/'requirements.lock')
    monkeypatch.setattr(module,'ROOT',root)
    monkeypatch.setenv('THREADGATE_MODEL','gemini-2.5-flash')
    return module


def fake_development(module,path):
    cases,_=module.verified_corpus(False)
    report={'unit_test_simulation':True,'split':'development','sample_size':len(cases),
        'configuration_fingerprint':module.configuration_identity()['sha256'],
        'model':'gemini-2.5-flash','cases':[{'id':c['id'],'provider_error_kind':None} for c in cases],
        'systems':{'threadgate_gemini':{'status':'RUN','gate':{'false_CLEAR':{'count':0},'missed_HOLD':{'count':0}}}}}
    path.write_text(json.dumps(report));return report


def freeze(module):
    report=module.ROOT/'simulated-development.json';fake_development(module,report)
    target=module.ROOT/'freeze.json';record=module.freeze_configuration(target,report)
    return target,record


def test_fingerprint_has_no_credential_dependency(evaluator,monkeypatch):
    first=evaluator.configuration_identity()
    monkeypatch.setenv('GEMINI_API_KEY','unit-test-placeholder-never-used')
    assert evaluator.configuration_identity()==first


@pytest.mark.parametrize('kind',['short_extraction','short_decisions','invalid_decision'])
def test_metric_helpers_refuse_missing_samples_and_invalid_labels(evaluator,kind):
    cases=[{'expected_decision':'HOLD','change_requested':True}]
    with pytest.raises(ValueError):
        if kind=='short_extraction':evaluator.extraction_metrics(cases,[])
        elif kind=='short_decisions':evaluator.gate_metrics(cases,[])
        else:evaluator.gate_metrics(cases,['APPROVED'])


def test_reserved_split_is_separate_not_combined(evaluator):
    development,_=evaluator.verified_corpus(False)
    heldout,_=evaluator.verified_corpus(True)
    assert len(development)==32 and len(heldout)==16
    assert not ({c['id'] for c in development}&{c['id'] for c in heldout})
    assert all(c['id'].startswith('AS-hel-') for c in heldout)
    # No evaluate/run_case call occurs: reading split metadata is not running it.


def test_freeze_requires_matching_live_development_evidence(evaluator):
    path=evaluator.ROOT/'simulated.json';report=fake_development(evaluator,path)
    report['systems']['threadgate_gemini']['status']='BLOCKED';path.write_text(json.dumps(report))
    with pytest.raises(ValueError):evaluator.freeze_configuration(evaluator.ROOT/'freeze.json',path)


def test_freeze_is_exclusive_and_checks_evidence_integrity(evaluator):
    path,record=freeze(evaluator)
    assert evaluator.check_freeze(path)==record
    with pytest.raises(FileExistsError):evaluator.freeze_configuration(path,evaluator.ROOT/'simulated-development.json')
    (evaluator.ROOT/'simulated-development.json').write_text('{}')
    with pytest.raises(ValueError):evaluator.check_freeze(path)


@pytest.mark.parametrize('kind',['source','model','reference'])
def test_changed_frozen_configuration_is_refused(evaluator,monkeypatch,kind):
    path,_=freeze(evaluator)
    if kind=='source':
        target=evaluator.ROOT/'src/threadgate/policy.py';target.write_text(target.read_text()+'\n# synthetic change\n')
    elif kind=='reference':
        target=evaluator.ROOT/'data/records/vendor_master.json';target.write_text(target.read_text()+'\n')
    else:monkeypatch.setenv('THREADGATE_MODEL','different-unit-test-model')
    with pytest.raises(ValueError):evaluator.check_freeze(path)


def test_consumption_survives_failure_and_rejects_rerun(evaluator):
    _,record=freeze(evaluator)
    path=evaluator.begin_heldout(record)
    assert json.loads(path.read_text())['consumed'] is True
    evaluator.finish_heldout(path,'FAILED')
    with pytest.raises(FileExistsError):evaluator.begin_heldout(record)
    assert json.loads(path.read_text())['status']=='FAILED'


def test_concurrent_consumption_allows_exactly_one_local_run(evaluator):
    _,record=freeze(evaluator)
    def begin(_):
        try:evaluator.begin_heldout(record);return 'started'
        except FileExistsError:return 'blocked'
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(begin,range(8)))
    assert results.count('started')==1 and results.count('blocked')==7


def test_frozen_labels_byte_preserved(evaluator):
    manifest=json.loads((evaluator.ROOT/'data/assurance/manifest.json').read_text())
    for name,digest in manifest['files'].items():
        assert hashlib.sha256((evaluator.ROOT/'data/assurance'/name).read_bytes()).hexdigest()==digest
    cases,manifest=evaluator.verified_corpus(False)
    report=evaluator.evaluate(cases[:1],manifest,False)
    assert report['cases'][0]['offline_extraction']['exact_annotated_field_accuracy']['sample_size']>=0
    assert report['cases'][0]['gemini_extraction'] is None
    assert report['cases'][0]['provider_observations']==[]


def test_single_case_smoke_calls_pipeline_once(monkeypatch):
    module=load('workflow_smoke',ROOT/'scripts/live_check.py')
    from threadgate.pipeline import run_case
    from threadgate.extract import offline_extract
    calls=[]
    def mocked(*args,**kwargs):
        calls.append(1);return run_case(*args,**kwargs,extractor_fn=offline_extract)
    monkeypatch.setattr(module,'run_case',mocked)
    report=module.run_checks(1)
    assert len(calls)==len(report['cases'])==1 and report['status']=='PASS'


def test_combined_split_flag_is_refused_without_provider(evaluator,monkeypatch):
    monkeypatch.setattr(evaluator,'evaluate',lambda *a,**k:pytest.fail('Must not interpret heldout'))
    assert evaluator.main(['--include-heldout'])==2
    assert evaluator.main(['--split','heldout'])==2


@pytest.mark.parametrize('kind',['expected','wrong-test','wrong-reason','setup-error'])
def test_mutation_checker_requires_expected_named_assertion(tmp_path,kind):
    import xml.etree.ElementTree as ET
    module=load('workflow_mutations',ROOT/'scripts/assurance_mutations.py')
    root=ET.Element('testsuites');suite=ET.SubElement(root,'testsuite')
    case=ET.SubElement(suite,'testcase',name='test_guard' if kind!='wrong-test' else 'test_other')
    element=ET.SubElement(case,'error' if kind=='setup-error' else 'failure')
    element.text='expected security assertion' if kind!='wrong-reason' else 'unrelated exception'
    path=tmp_path/'result.xml';ET.ElementTree(root).write(path)
    found=module.expected_failures(path,'test_guard',['expected security assertion'])
    assert bool(found)==(kind=='expected')
