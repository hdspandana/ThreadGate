"""Explicit opt-in Gemini smoke check, using only synthetic corpus data.

Exit 2: missing configuration; 1: API/schema or sampled policy mismatch; 0: pass.
This is a small integration check, not an independent performance benchmark.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
import hashlib
import importlib.metadata
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from threadgate.config import load_environment,key_configured,check_settings
from threadgate.records import load_cases,load_vendors
from threadgate.pipeline import run_case
from threadgate.clock import fixed
from threadgate.reporting import case_report
from threadgate.schema import Extraction


def run_checks(case_count=3):
    cases=load_cases(ROOT/'data/cases/frozen_v1.json')
    vendors=load_vendors(ROOT/'data/records/vendor_master.json')
    selected=[next(c for c in cases if c['expected_decision']==label) for label in ['HOLD','REVIEW','CLEAR']]
    selected=selected[:case_count]
    rows=[]
    for case in selected:
        result=run_case(case,vendors,extractor_mode='gemini',clock=fixed('2026-10-06'))
        rows.append({'case':case['id'],'expected':case['expected_decision'],
                     'passed':not result.error and result.decision.decision==case['expected_decision'],
                     'report':case_report(result),'provider_error_kind':result.error_kind,'provider_observations':result.provider_events})
    return {'generated_at':datetime.now(timezone.utc).isoformat(),
            'model':os.getenv('THREADGATE_MODEL','gemini-2.5-flash'),
            'extractor_code_sha256':hashlib.sha256((ROOT/'src/threadgate/extract.py').read_bytes()).hexdigest(),
            'evaluation_version':'gemini-smoke-v3','sdk_version':importlib.metadata.version('google-genai'),
            'schema_sha256':hashlib.sha256(json.dumps(Extraction.model_json_schema(),sort_keys=True).encode()).hexdigest(),
            'config':{'timeout_ms':int(os.getenv('THREADGATE_HTTP_TIMEOUT_MS','30000')),'budget_ms':int(os.getenv('THREADGATE_TOTAL_BUDGET_MS','90000')),'max_attempts':3},
            'as_of':'2026-10-06','status':'PASS' if all(r['passed'] for r in rows) else 'FAIL',
            'scope':f'{len(rows)} synthetic integration case(s); not a field error-rate estimate.',
            'cases':rows}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases',type=int,choices=[1,3],default=1,help='Start with one low-cost case; three-case integration check is optional.')
    parser.add_argument('--output',default=str(ROOT/'data/runs/live-smoke.json'))
    args=parser.parse_args(argv)
    load_environment(ROOT)
    if not key_configured() or check_settings():
        print('Live check not run: configure a non-placeholder key and valid timeout settings. No API call made.')
        return 2
    print(f'COST NOTICE: {args.cases} synthetic case(s), at most {args.cases*3} outer provider attempts; billing cost is unknown.')
    try:
        report=run_checks(args.cases)
    except Exception:
        print('Live check failed before completion. No successful result is claimed; check provider access and configuration.')
        return 1
    output=Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    return 0 if report['status']=='PASS' else 1


if __name__=='__main__':
    raise SystemExit(main())
