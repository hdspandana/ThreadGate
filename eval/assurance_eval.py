"""Frozen synthetic extraction + gate evaluation, default OFFLINE.

Live mode reuses each Gemini extraction for the full gate, never asking Gemini
for a verdict. Heldout is reserved and must be explicitly unlocked for a final run.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import statistics
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from threadgate.clock import fixed
from threadgate.compare import normalize_value
from threadgate.config import load_environment,key_configured,check_settings
from threadgate.pipeline import run_case
from threadgate.records import load_vendors
from threadgate.schema import Extraction
from threadgate.baseline import rules_only_normalized
VERSION='assurance-eval-v3'


def rate(count,total):
    return {'count':count,'sample_size':total,'rate':count/total if total else None}


def extraction_metrics(cases,results):
    if len(cases)!=len(results):raise ValueError('Case/result count mismatch; metrics refused.')
    changes=sum(c['change_requested'] for c in cases)
    detected=correct_fields=fields=extra=incomplete=invalid=schema=provider=timeouts=0
    for case,result in zip(cases,results):
        gold={f:{normalize_value(f,v) for v in (values if isinstance(values,list) else [values])}
              for f,values in case['expected_fields'].items()}
        predicted={}
        if not result.error:
            for claim in result.extraction.claims:
                if claim.new_value is not None:
                    predicted.setdefault(claim.field,set()).add(normalize_value(claim.field,claim.new_value))
            detected+=bool(case['change_requested'] and result.extraction.intent=='change_request')
        fields+=len(gold)
        correct_fields+=sum(predicted.get(f,set())==values for f,values in gold.items())
        extra+=len(set(predicted)-set(gold))
        partial=any(f not in predicted for f in gold)
        incomplete+=partial
        invalid+=bool(result.error or partial or any(not c.verified for c in result.validation.claims))
        schema+=result.error_kind=='schema'
        provider+=bool(result.error and result.error_kind!='schema')
        timeouts+=result.error_kind=='timeout'
    n=len(cases)
    return {'exact_annotated_field_accuracy':rate(correct_fields,fields),
        'unannotated_predicted_fields':{'count':extra,'cases':n,'note':'Diagnostic only; annotation is sparse, not every extra field is wrong.'},
        'change_request_intent_recall':rate(detected,changes),
        'change_request_intent_false_negative_rate':rate(changes-detected,changes),
        'invalid_or_incomplete_extraction':rate(invalid,n),'incomplete_annotated_fields':rate(incomplete,n),
        'schema_failure':rate(schema,n),'provider_failure':rate(provider,n),'provider_timeout':rate(timeouts,n)}


def gate_metrics(cases,decisions):
    if len(cases)!=len(decisions):raise ValueError('Case/decision count mismatch; metrics refused.')
    if any(d not in {'CLEAR','REVIEW','HOLD'} for d in decisions):raise ValueError('Invalid gate decision.')
    nonclear=sum(c['expected_decision']!='CLEAR' for c in cases)
    changes=sum(c['change_requested'] for c in cases)
    holds=sum(c['expected_decision']=='HOLD' for c in cases)
    nothold=len(cases)-holds;notreview=sum(c['expected_decision']!='REVIEW' for c in cases)
    return {'change_gate_recall':rate(sum(c['change_requested'] and d!='CLEAR' for c,d in zip(cases,decisions)),changes),
        'change_gate_false_negative_rate':rate(sum(c['change_requested'] and d=='CLEAR' for c,d in zip(cases,decisions)),changes),
        'decision_accuracy':rate(sum(c['expected_decision']==d for c,d in zip(cases,decisions)),len(cases)),
        'false_CLEAR':rate(sum(c['expected_decision']!='CLEAR' and d=='CLEAR' for c,d in zip(cases,decisions)),nonclear),
        'missed_HOLD':rate(sum(c['expected_decision']=='HOLD' and d!='HOLD' for c,d in zip(cases,decisions)),holds),
        'false_HOLD':rate(sum(c['expected_decision']!='HOLD' and d=='HOLD' for c,d in zip(cases,decisions)),nothold),
        'false_REVIEW':rate(sum(c['expected_decision']!='REVIEW' and d=='REVIEW' for c,d in zip(cases,decisions)),notreview)}


def latency(results):
    values=sorted(r.elapsed_ms for r in results)
    return {'sample_size':len(values),'median_ms':statistics.median(values) if values else None,
            'p95_ms':values[max(0,math.ceil(.95*len(values))-1)] if values else None}


def verified_corpus(include_heldout=False):
    folder=ROOT/'data/assurance'
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    for name,digest in manifest['files'].items():
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Frozen corpus digest mismatch.')
    cases=json.loads((folder/'development.json').read_text(encoding='utf-8'))['cases']
    if include_heldout:cases=json.loads((folder/'heldout.json').read_text(encoding='utf-8'))['cases']
    if len({c['id'] for c in cases})!=len(cases):raise ValueError('Duplicate corpus case IDs.')
    return cases,manifest


def smoke_valid(path):
    try:
        smoke=json.loads(Path(path).read_text())
        age=(datetime.now(timezone.utc)-datetime.fromisoformat(smoke['generated_at'])).total_seconds()
        return (smoke['status']=='PASS' and smoke['model']==os.getenv('THREADGATE_MODEL','gemini-2.5-flash')
            and 0<=age<=86400 and len(smoke['cases'])>=1
            and smoke['schema_sha256']==hashlib.sha256(json.dumps(Extraction.model_json_schema(),sort_keys=True).encode()).hexdigest()
            and smoke['extractor_code_sha256']==hashlib.sha256((ROOT/'src/threadgate/extract.py').read_bytes()).hexdigest()
            and smoke['sdk_version']==importlib.metadata.version('google-genai')
            and smoke['config']=={'timeout_ms':int(os.getenv('THREADGATE_HTTP_TIMEOUT_MS','30000')),'budget_ms':int(os.getenv('THREADGATE_TOTAL_BUDGET_MS','90000')),'max_attempts':3}
            and all(row['passed'] and not row['report']['model_error'] and row['report']['extractor']=='gemini' for row in smoke['cases']))
    except (OSError,ValueError,KeyError,TypeError):return False


def corpus_assurance(cases):
    """Claim limits, not alternative gold labels or an independently reviewed score.

    Keep every case in the existing denominators; record why those denominators
    describe author-defined regression agreement, not field effectiveness.
    """
    decisions={label:sum(c['expected_decision']==label for c in cases) for label in ['HOLD','REVIEW','CLEAR']}
    fields={}
    for case in cases:
        for name in case['expected_fields']:fields[name]=fields.get(name,0)+1
    return {'review_version':'agent-design-review-v1',
        'label_review_status':'AGENT_REVIEW_ONLY_NOT_INDEPENDENTLY_ADJUDICATED',
        'expected_decision_counts':decisions,'annotated_case_field_counts':fields,
        'template_families':len({c['category'] for c in cases}),
        'active_request_label_dispute_ids':[c['id'] for c in cases if c['category']=='forwarded_stale'],
        'empty_field_annotation_ids':[c['id'] for c in cases if not c['expected_fields']],
        'metric_interpretation':'Agreement with immutable author-defined labels; no relabelling or exclusion applied.',
        'limitations':[
            'Development variants and heldout paraphrases share semantic template families and destinations; text separation is not independent distribution separation.',
            'Forwarded-history gold may conflate quoted/unchanged values with active requested changes; independent adjudication is outstanding.',
            'Sparse requested-field gold does not establish field precision or hallucination rates; most annotated fields are account numbers.',
            'Ambiguous/conflicting/malformed instructions permit plausible abstention; field fidelity is not a financial safety decision.',
            'Small imbalanced synthetic sets cannot establish real-world accuracy, fraud prevention or production readiness.']}


def evaluate(cases,manifest,live=False):
    vendors=load_vendors(ROOT/'data/records/vendor_master.json')
    clock=fixed('2026-10-06')
    offline=[run_case(c,vendors,extractor_mode='offline',clock=clock) for c in cases]
    # Missing-vendor rules baseline has no reference to compare: explicitly HOLD.
    rules=[rules_only_normalized(c,vendors[c['vendor_id']]).decision if c['vendor_id'] in vendors else 'HOLD' for c in cases]
    rows={'deterministic_rules':{'status':'RUN','gate':gate_metrics(cases,rules),'raw_extraction':None},
          'offline_test_double':{'status':'RUN','not_model_performance':True,'extraction':extraction_metrics(cases,offline),
                                 'gate':gate_metrics(cases,[r.decision.decision for r in offline]),'latency':latency(offline)}}
    model_results=[]
    if live:
        model_results=[run_case(c,vendors,extractor_mode='gemini',clock=clock) for c in cases]
        rows['gemini_interpretation']={'status':'RUN','extraction':extraction_metrics(cases,model_results),
            'note':'Raw Extraction scored before evidence validation; exact same response used by final gate.'}
        rows['threadgate_gemini']={'status':'RUN','gate':gate_metrics(cases,[r.decision.decision for r in model_results]),'latency':latency(model_results)}
    else:
        rows['gemini_interpretation']={'status':'BLOCKED','sample_size':0,'reason':'No opt-in live run.'}
        rows['threadgate_gemini']={'status':'BLOCKED','sample_size':0,'reason':'No opt-in live run.'}
    observations=[e for r in model_results for e in r.provider_events]
    tokens={name:sum(e.get(name,0) for e in observations) for name in ['prompt_token_count','candidates_token_count','total_token_count']}
    return {'evaluation_version':VERSION,'generated_at':datetime.now(timezone.utc).isoformat(),
        'schema_sha256':hashlib.sha256(json.dumps(Extraction.model_json_schema(),sort_keys=True).encode()).hexdigest(),
        'extractor_code_sha256':hashlib.sha256((ROOT/'src/threadgate/extract.py').read_bytes()).hexdigest(),
        'sdk_version':importlib.metadata.version('google-genai'),
        'reference_as_of':'2026-10-06','model':os.getenv('THREADGATE_MODEL','gemini-2.5-flash') if live else None,
        'config':{'timeout_ms':int(os.getenv('THREADGATE_HTTP_TIMEOUT_MS','30000')),'budget_ms':int(os.getenv('THREADGATE_TOTAL_BUDGET_MS','90000')),'max_attempts':3},
        'configuration_fingerprint':configuration_identity()['sha256'],
        'split':'heldout' if cases and all(c['id'].startswith('AS-hel-') for c in cases) else 'development',
        'corpus':manifest,'corpus_assurance':corpus_assurance(cases),'sample_size':len(cases),'systems':rows,'observed_provider_tokens':tokens if observations else None,
        'measured_cost':None,'cost_note':'Provider billing not available. Token counts cover observed responses only; failed calls may also be billed.',
        'limitations':['Sparse field labels; not a field error estimate.','Synthetic author knew design; reserved holdout is not independent human-authored validation.',
                       'An unavailable/ambiguous vendor is marked unresolved by the caller, not inferred from account similarity.',
                       'Duplicate/replay guarantees are measured by service tests, not email-classification labels.'],
        'cases':[{'id':c['id'],'category':c['category'],'expected':c['expected_decision'],
                  'offline':r.decision.decision,
                  'offline_extraction':extraction_metrics([c],[r]),
                  'gemini_extraction':extraction_metrics([c],[model_results[i]]) if live else None,
                  'gemini_latency_ms':model_results[i].elapsed_ms if live else None,
                  'provider_observations':model_results[i].provider_events if live else [],
                  'controls':[f.code for f in r.decision.findings],
                  'gemini':model_results[i].decision.decision if live else None,
                  'provider_error_kind':model_results[i].error_kind if live else None}
                 for i,(c,r) in enumerate(zip(cases,offline))]}


def configuration_identity():
    """Freeze all application/control code, evaluator, records, lock and settings.

    No key or credential-derived fingerprint is ever included. This is a local
    unsigned reproducibility record, not external proof of untampered execution.
    """
    paths=list((ROOT/'src/threadgate').glob('*.py'))
    paths += [ROOT/'eval/assurance_eval.py',ROOT/'data/records/vendor_master.json',
              ROOT/'data/assurance/manifest.json',ROOT/'requirements.lock']
    files={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    value={'files':files,'model':os.getenv('THREADGATE_MODEL','gemini-2.5-flash'),
           'sdk_version':importlib.metadata.version('google-genai'),
           'config':{'timeout_ms':int(os.getenv('THREADGATE_HTTP_TIMEOUT_MS','30000')),
                     'budget_ms':int(os.getenv('THREADGATE_TOTAL_BUDGET_MS','90000')),'max_attempts':3}}
    return {'sha256':hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest(),'identity':value}


def freeze_configuration(target,development_report):
    cases,manifest=verified_corpus(False)
    report_path=Path(development_report).resolve()
    report=json.loads(report_path.read_text())
    identity=configuration_identity()
    if (report.get('split')!='development' or report.get('sample_size')!=len(cases)
        or report.get('configuration_fingerprint')!=identity['sha256']
        or report.get('model')!=identity['identity']['model']
        or [r['id'] for r in report.get('cases',[])]!=[c['id'] for c in cases]
        or report.get('systems',{}).get('threadgate_gemini',{}).get('status')!='RUN'
        or any(r.get('provider_error_kind') for r in report.get('cases',[]))):
        raise ValueError('Matching successful live development report required.')
    gate=report['systems']['threadgate_gemini']['gate']
    if gate['false_CLEAR']['count'] or gate['missed_HOLD']['count']:
        raise ValueError('Development safety failure must be resolved before freezing.')
    target=Path(target).resolve();target.parent.mkdir(parents=True,exist_ok=True)
    record={'protocol':'threadgate-frozen-evaluation-v1','frozen_at':datetime.now(timezone.utc).isoformat(),
            'configuration':identity,'corpus':manifest,
            'development_report':os.path.relpath(report_path,target.parent),
            'development_report_sha256':hashlib.sha256(report_path.read_bytes()).hexdigest(),
            'trust':'Unsigned local record. Privileged rewriting/deletion defeats local guards.'}
    with target.open('x') as stream:json.dump(record,stream,indent=2);stream.write('\n')
    return record


def check_freeze(path):
    path=Path(path).resolve();record=json.loads(path.read_text())
    if record.get('protocol')!='threadgate-frozen-evaluation-v1' or record['configuration']!=configuration_identity():
        raise ValueError('Frozen configuration changed; heldout evaluation refused.')
    development=path.parent/record['development_report']
    if hashlib.sha256(development.read_bytes()).hexdigest()!=record['development_report_sha256']:
        raise ValueError('Frozen development evidence changed.')
    return record


def begin_heldout(record):
    # Consume BEFORE any provider call, including failed/interrupted attempts.
    # Exclusive create protects concurrent local runs. A privileged filesystem
    # writer can delete this ledger; this is not an external audit authority.
    digest=record['corpus']['files']['heldout.json']
    folder=ROOT/'data/runs/heldout-ledger';folder.mkdir(parents=True,exist_ok=True)
    path=folder/(digest+'.json')
    value={'heldout_sha256':digest,'configuration_fingerprint':record['configuration']['sha256'],
           'started_at':datetime.now(timezone.utc).isoformat(),'status':'STARTED','consumed':True}
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    return path


def finish_heldout(path,status):
    value=json.loads(path.read_text());value['status']=status
    value['finished_at']=datetime.now(timezone.utc).isoformat()
    # The original consumed marker is never removed, even on an interrupted write.
    with path.open('w') as stream:json.dump(value,stream,indent=2);stream.write('\n')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--confirm-cost',action='store_true')
    parser.add_argument('--split',choices=['development','heldout'],default='development')
    parser.add_argument('--include-heldout',action='store_true',help='Legacy flag rejected: splits must run separately.')
    parser.add_argument('--confirm-heldout-final-run',action='store_true')
    parser.add_argument('--freeze-file')
    parser.add_argument('--freeze-config')
    parser.add_argument('--development-report')
    parser.add_argument('--confirm-development-reviewed',action='store_true')
    parser.add_argument('--smoke-report',default=str(ROOT/'data/runs/live-smoke.json'))
    parser.add_argument('--output')
    args=parser.parse_args(argv);load_environment(ROOT)
    if check_settings():print('Invalid provider configuration.');return 2
    if args.include_heldout:
        print('Combined development/heldout runs are refused. Use --split heldout with a frozen configuration.');return 2
    if args.freeze_config:
        if not args.development_report or not args.confirm_development_reviewed:
            print('Review development failures first; provide --development-report and --confirm-development-reviewed.');return 2
        try:freeze_configuration(args.freeze_config,args.development_report)
        except (OSError,ValueError,KeyError,TypeError):
            print('Freeze refused: require new output and intact matching live development evidence.');return 2
        print('Configuration frozen locally. Heldout has NOT been run.');return 0
    heldout=args.split=='heldout'
    if heldout and not (args.live and args.confirm_heldout_final_run and args.freeze_file):
        print('Heldout reserved: require live opt-in, final-run confirmation and a frozen configuration.');return 2
    if args.live:
        print('COST WARNING: one extraction per case, at most three outer attempts; billing cost unknown. Development=32 cases, heldout=16 cases, run separately.')
        if not args.confirm_cost or not key_configured() or not smoke_valid(args.smoke_report):
            print('BLOCKED: configure key, pass a matching smoke check in the past 24 hours, and pass --confirm-cost.');return 2
    marker=None
    try:
        cases,manifest=verified_corpus(heldout)
        target=Path(args.output or str(ROOT/('data/runs/assurance-heldout.json' if heldout else 'data/runs/assurance-evaluation.json')))
        if heldout:
            record=check_freeze(args.freeze_file)
            if target.exists():raise FileExistsError('Preserve previous heldout evidence.')
            marker=begin_heldout(record)
        report=evaluate(cases,manifest,args.live)
        if [row['id'] for row in report['cases']]!=[c['id'] for c in cases]:raise ValueError('Report alignment failure.')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(report,indent=2)+'\n')
        gate=report['systems']['threadgate_gemini' if args.live else 'offline_test_double']['gate']
        failed=bool(gate['false_CLEAR']['count'] or gate['missed_HOLD']['count'] or
                    (args.live and any(row['provider_error_kind'] for row in report['cases'])))
        if marker:finish_heldout(marker,'FAILED' if failed else 'COMPLETE')
    except Exception as exc:
        if marker:finish_heldout(marker,'FAILED')
        print('Evaluation refused or failed:',type(exc).__name__,'. Existing heldout consumption is never reset.');return 1
    print('Wrote',target,'with',report['sample_size'],'synthetic cases; split=',args.split,'live=',args.live)
    return 1 if failed else 0


if __name__=='__main__':raise SystemExit(main())
