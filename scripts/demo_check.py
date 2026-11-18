"""Small synthetic, no-provider demo preflight; never modifies reference records.

Run: python -B scripts/demo_check.py
These are pipeline checks, not browser, Gemini, identity or payment validation.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from threadgate.pipeline import run_case
from threadgate.records import load_cases,load_vendors
from threadgate.schema import Extraction


def check():
    vendors=load_vendors(ROOT/'data/records/vendor_master.json')
    fixtures={c['id']:c for c in load_cases(ROOT/'data/cases/frozen_v1.json')}
    rows=[]

    def evaluate(name,case,expected,mode='offline',extractor=None):
        try:
            result=run_case(copy.deepcopy(case),vendors,extractor_mode=mode,extractor_fn=extractor)
            actual=result.decision.decision
            details={'reference':result.decision.reference_state,'error_kind':result.error_kind,
                     'findings':[f.code for f in result.decision.findings]}
        except ValueError:
            actual='REJECTED';details={'validation_error':True}
        rows.append(dict(name=name,expected=expected,actual=actual,passed=actual==expected,**details))

    for cid,expected in [('TG-007','CLEAR'),('TG-012','REVIEW'),('TG-001','HOLD'),('TG-020','HOLD')]:
        evaluate(cid,fixtures[cid],expected)
    def pasted(body,vendor_id='V-1001'):
        return {'vendor_id':vendor_id,'email':{'body':body,'subject':'Synthetic demo request','from':''}}
    evaluate('paste-no-change',pasted('No change to our payment details.'),'CLEAR')
    evaluate('paste-reviewed-alternate',pasted(fixtures['TG-012']['email']['body']),'REVIEW')
    evaluate('paste-new-destination',pasted(fixtures['TG-001']['email']['body']),'HOLD')
    evaluate('unknown-destination',pasted('Please update account number: 98989898989898.'),'HOLD')
    evaluate('malformed-destination',pasted('Please update account number: ABCD1234567890.'),'HOLD')
    evaluate('missing-vendor',pasted('No payment details are changing.','DEMO-MISSING'),'HOLD')
    evaluate('compromised-output',fixtures['TG-001'],'HOLD',mode='compromised')
    def failure(*args,**kwargs):raise RuntimeError('synthetic adapter unavailable')
    evaluate('adapter-failure',fixtures['TG-001'],'HOLD',extractor=failure)
    evaluate('invented-evidence',fixtures['TG-001'],'HOLD',extractor=lambda *a,**k:
        Extraction(intent='no_change',intent_evidence='This sentence is not in the input.',claims=[]))
    evaluate('invalid-body-type',pasted(None),'REJECTED')
    evaluate('oversized-input',pasted('x'*22001),'REJECTED')
    return {'scope':'Synthetic pipeline only; no provider, browser, authenticated workflow or payment calls',
            'runtime_utc':datetime.now(timezone.utc).isoformat(),
            'passed':sum(row['passed'] for row in rows),'total':len(rows),'rows':rows}


def main():
    report=check()
    print(json.dumps(report,indent=2))
    return 0 if report['passed']==report['total'] else 1


if __name__=='__main__':raise SystemExit(main())
