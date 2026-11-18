"""One-command, key-independent validation. Never loads local API secrets.

Logs are written under ignored data/runs/release-check. A source ZIP without Git
history gets WARN, not a claim that history was scanned. Use --require-history
from a clone before pushing. Use live_check.py separately after adding a key.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
ROOT=Path(__file__).resolve().parents[1]


def commands(test_xml=None):
    return [('preflight',['scripts/doctor.py']),
            ('tests',['-m','pytest','-o','addopts=','-q','--junitxml',str(test_xml or ROOT/'data/runs/release-check/tests.xml')]),
            ('kill-gate',['scripts/kill_gate.py']),
            ('secret-audit',['scripts/secret_scan.py','--allow-local-secrets']),
            ('offline-evaluation',['eval/run_eval.py','--out',str(ROOT/'data/runs/release-check/evaluation')]),
            ('assurance-evaluation',['eval/assurance_eval.py','--output',str(ROOT/'data/runs/release-check/assurance-evaluation.json')]),
            ('attack-matrix',['scripts/attack_report.py','--output',str(ROOT/'data/runs/release-check/attack-report.json')]),
            ('assurance-mutations',['scripts/assurance_mutations.py']),
            ('isolated-recovery',['scripts/recovery_check.py']),
            ('source-compilation',['-m','compileall','-q','src','app','scripts']),
            ('source-package',['scripts/package_release.py']),
            ('archive-integrity',['scripts/verify_release.py'])]


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-history',action='store_true')
    args=parser.parse_args(argv)
    try:
        from scripts.validation_evidence import test_summary, write_evidence, invalidate_evidence, validate_test_outcomes
    except ModuleNotFoundError:
        from validation_evidence import test_summary, write_evidence, invalidate_evidence, validate_test_outcomes
    invalidate_evidence(ROOT,'source')
    output=ROOT/'data/runs/release-check'
    output.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ)
    for key in ('GEMINI_API_KEY','GOOGLE_API_KEY'):
        env.pop(key,None)
    env['THREADGATE_SKIP_DOTENV']='1'
    results=[]
    test_counts=test_summary()
    # Unique XML prevents a failed pytest startup from reusing old passing counts.
    test_xml=output/('tests-'+uuid.uuid4().hex+'.xml')
    for name,parts in commands(test_xml):
        print('Checking '+name+'…',flush=True)
        exit_code=None
        try:
            proc=subprocess.run([sys.executable,*parts],cwd=ROOT,env=env,capture_output=True,text=True,timeout=600)
            exit_code=proc.returncode
            text=proc.stdout+proc.stderr
            status='PASS' if proc.returncode==0 else 'FAIL'
            if name=='secret-audit' and proc.returncode==3 and not args.require_history:
                status='WARN'
        except subprocess.TimeoutExpired:
            text='Step exceeded 600-second process limit. Not a passing result.'
            status='FAIL'
        if name=='tests':
            test_counts=test_summary(test_xml,text)
            try:validate_test_outcomes(test_counts,'source' if args.require_history else 'fresh-extracted')
            except ValueError:
                status='FAIL'
                text='Required test evidence unavailable or unsuccessful.'
        (output/(name+'.txt')).write_text(text)
        results.append({'step':name,'status':status,'command':[sys.executable,*parts],'exit_code':exit_code})
        print(name+': '+status,flush=True)
        if status=='FAIL':
            print(text[-5000:])
            break
    report={'generated_at':datetime.now(timezone.utc).isoformat(),
            'status':'FAIL' if any(r['status']=='FAIL' for r in results) else 'PASS',
            'network_api_tested':False,'history_required':args.require_history,'steps':results,
            'tests':test_counts}
    (output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    write_evidence(ROOT,'source',report['status'],test_counts,results)
    print(json.dumps(report,indent=2))
    return 1 if report['status']=='FAIL' else 0


if __name__=='__main__':
    raise SystemExit(main())
