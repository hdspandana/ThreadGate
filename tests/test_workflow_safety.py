"""Focused malformed-adapter and privacy boundary regressions; synthetic only."""
import re
from pathlib import Path
import pytest
from threadgate.clock import fixed
from threadgate.records import load_vendors
from threadgate.pipeline import run_case
from threadgate.schema import Extraction,Claim
from threadgate.presentation import masked_text

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('bad',[None,{},'not structured',{'intent':'APPROVED'},Extraction.model_construct(intent='APPROVED')],
                         ids=['missing','empty','string','invalid-intent','constructed-invalid-model'])
def test_malformed_adapter_result_is_schema_failure_and_hold(bad):
    case={'id':'WF-MALFORMED','vendor_id':'V-1001','email':{'body':'Our account remains unchanged.'}}
    result=run_case(case,load_vendors(ROOT/'data/records/vendor_master.json'),
        extractor_fn=lambda *a,**k:bad,clock=fixed('2026-10-06'))
    assert result.decision.decision=='HOLD'
    assert result.error_kind=='schema' and result.error


@pytest.mark.parametrize('intent',['no_change','unverifiable','change_request'])
def test_low_confidence_or_suppressed_change_cannot_release_destination(intent):
    body='Please update account number: 50100234559821.'
    extraction=Extraction(intent=intent,intent_evidence=body,claims=[] if intent!='change_request' else
        [Claim(field='account_number',new_value='50100234559821',evidence=body,confidence=0)])
    result=run_case({'id':'WF-LOW-CONFIDENCE','vendor_id':'V-1001','email':{'body':body}},
        load_vendors(ROOT/'data/records/vendor_master.json'),extractor_fn=lambda *a,**k:extraction,clock=fixed('2026-10-06'))
    assert result.decision.decision=='HOLD'
    assert any(f.independent_of_model for f in result.decision.findings)


def test_overlapping_mask_matches_do_not_expose_long_identifier_tail():
    text='Account number: '+('1234567890'*8)+'.'
    masked=masked_text(text)
    assert '••••' in masked
    assert not re.search(r'\d{5,}',masked), 'Only the intended last four digits may remain visible'
