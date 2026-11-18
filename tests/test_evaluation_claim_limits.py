"""Claim qualifications must never repair labels, hide cases or imply independence."""
import copy
import importlib.util
from pathlib import Path
import hashlib
from dotenv import dotenv_values
ROOT=Path(__file__).resolve().parents[1]


def evaluator():
    spec=importlib.util.spec_from_file_location('claim_limits_eval',ROOT/'eval/assurance_eval.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_corpus_claim_qualification_preserves_all_development_labels():
    module=evaluator();cases,manifest=module.verified_corpus(False);before=copy.deepcopy(cases)
    review=module.corpus_assurance(cases)
    assert cases==before
    assert review['expected_decision_counts']=={'HOLD':28,'REVIEW':2,'CLEAR':2}
    assert review['active_request_label_dispute_ids']==['AS-dev-05-1','AS-dev-05-2']
    report=module.evaluate(cases,manifest,False)
    assert report['sample_size']==32 and len(report['cases'])==32
    assert report['corpus_assurance']['label_review_status']=='AGENT_REVIEW_ONLY_NOT_INDEPENDENTLY_ADJUDICATED'
    assert report['systems']['offline_test_double']['gate']['decision_accuracy']['sample_size']==32
    assert report['systems']['gemini_interpretation']['sample_size']==0


def test_original_corpus_and_manifest_byte_identical_to_starting_release():
    # Independently recorded starting-release digests, usable without Git too.
    expected={'development.json': '5da0ffa0f7ae6270b446521abaae4fd64ef730de5809b144fa5a9eccac9a5586', 'heldout.json': '3efcf0b7bd7d530623a9571ff0d32d29f65def4a7427ca3d6839fe01240c7f0b', 'manifest.json': 'c33d452f79f59816491203cbe86bac4584a5cf5d522a0aea6b29159d52fd4c5f'}
    for name,digest in expected.items():
        assert hashlib.sha256((ROOT/'data/assurance'/name).read_bytes()).hexdigest()==digest


def test_public_overlay_enforces_mfa_despite_optional_local_template():
    assert dotenv_values(ROOT/'.env.example')['THREADGATE_REQUIRE_MFA']=='0'
    overlay=(ROOT/'deployment/compose.public.yaml').read_text()
    assert 'THREADGATE_REQUIRE_MFA: "1"' in overlay
    assert '${THREADGATE_REQUIRE_MFA' not in overlay
