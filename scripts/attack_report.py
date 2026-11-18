"""Reproducible synthetic Attack Lab: actual pipeline with labelled model simulations."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'eval')]
from assurance_eval import verified_corpus
from threadgate.records import load_vendors
from threadgate.pipeline import run_case
from threadgate.clock import fixed


def generate():
    cases,_=verified_corpus(False)
    cases=[c for c in cases if c['id'].endswith('-1')]
    vendors=load_vendors(ROOT/'data/records/vendor_master.json')
    rows=[]
    for case in cases:
        for mode in ('offline','compromised','compromised_quote'):
            result=run_case(case,vendors,extractor_mode=mode,clock=fixed('2026-10-06'))
            rows.append({'id':case['id'],'category':case['category'],'engine':mode,
                'synthetic':True,'simulated_model':mode!='offline',
                'input':case['email'],'trusted_vendor':case['vendor_id'],
                'trusted_reference':vendors[case['vendor_id']].data if case['vendor_id'] in vendors else None,
                'interpretation':result.extraction.model_dump(),'diff':[d.model_dump() for d in result.decision.diffs],
                'expected':case['expected_decision'],'actual':result.decision.decision,
                'status':'PASS' if result.correct else 'FAIL',
                'expected_property':case['security_property'],'matches_label':result.correct,
                'unsafe_release':result.non_clear_release or result.unsafe,
                'controls':[{'code':f.code,'model_independent':f.independent_of_model} for f in result.decision.findings],
                'residual_limitation':case['limitation']})
    return {'version':'attack-report-v1','as_of':'2026-10-06','provider_called':False,
            'scope':'Synthetic actual-pipeline runs; simulated compromised output is not an actual provider compromise.',
            'runs':len(rows),'unsafe_releases':sum(bool(r['unsafe_release']) for r in rows),'rows':rows}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',default=str(ROOT/'data/runs/attack-report.json'))
    args=p.parse_args(argv);report=generate();target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,indent=2)+'\n')
    print('Synthetic Attack Lab:',report['runs'],'runs;',report['unsafe_releases'],'unsafe releases. Details:',target)
    return 1 if report['unsafe_releases'] else 0


if __name__=='__main__':raise SystemExit(main())
