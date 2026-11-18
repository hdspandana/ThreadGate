"""Portable packet integrity; preparation is never independent adjudication."""
import hashlib
import importlib.util
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def builder():
    spec=importlib.util.spec_from_file_location('review_packet',ROOT/'scripts/prepare_annotation_review.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_review_packet_reproducible_and_whitelisted():
    packet,coordinator=builder().build()
    assert packet==json.loads((ROOT/'docs/adjudication-v1/review-input.json').read_text())
    mapping=ROOT/'docs/adjudication-v1/COORDINATOR-ONLY.json'
    if mapping.exists():
        assert coordinator==json.loads(mapping.read_text())
    else:
        # Public export excludes private coordinator files, without skipping checks.
        assert (ROOT/'RELEASE_IDENTITY.json').is_file()
        assert len(coordinator['mapping'])==3
        assert {r['source_id'] for r in coordinator['mapping']}==set(builder().SELECTION)
    assert len(packet['cases'])==3
    for case in packet['cases']:
        assert set(case)=={'review_id','email'}
        assert set(case['email'])=={'from','reply_to','subject','body'}
    text=json.dumps(packet)
    for excluded in ('expected','prediction','AS-dev','AS-hel','50100234559821','50100234554455','HOLD','CLEAR'):
        assert excluded not in text
    assert packet['status']=='AWAITING_INDEPENDENT_HUMAN_REVIEW'


def test_original_corpus_bytes_and_coordinator_mapping_unchanged():
    expected={'development':'5da0ffa0f7ae6270b446521abaae4fd64ef730de5809b144fa5a9eccac9a5586',
              'heldout':'3efcf0b7bd7d530623a9571ff0d32d29f65def4a7427ca3d6839fe01240c7f0b',
              'manifest':'c33d452f79f59816491203cbe86bac4584a5cf5d522a0aea6b29159d52fd4c5f'}
    for name,digest in expected.items():
        assert hashlib.sha256((ROOT/'data/assurance'/f'{name}.json').read_bytes()).hexdigest()==digest
    _,mapping=builder().build()
    assert {row['source_id'] for row in mapping['mapping']}==set(builder().SELECTION)
    assert mapping['original_labels_modified'] is False


def test_response_template_contains_no_fabricated_human_labels():
    template=json.loads((ROOT/'docs/adjudication-v1/RESPONSE-TEMPLATE.json').read_text())
    assert template['independent_human_review_completed'] is False
    assert template['reviewer_code']==''
    assert [c['review_id'] for c in template['cases']]==['R01','R02','R03']
    assert all(not c['current_intent'] and not c['mentions'] and not c['requested_changes'] for c in template['cases'])
