"""Allowlisted numeric validation evidence. Never emit test names or raw output."""
from __future__ import annotations
import json
import os
from pathlib import Path
import re
import sys
import subprocess
import xml.etree.ElementTree as ET

PHASES = {'source', 'fresh-extracted'}
STATUSES = {'PASS', 'FAIL', 'WARN', 'NOT RUN', 'UNAVAILABLE'}
STEPS = {'preflight', 'tests', 'kill-gate', 'secret-audit', 'offline-evaluation',
         'assurance-evaluation', 'attack-matrix', 'assurance-mutations',
         'isolated-recovery', 'source-compilation', 'source-package', 'archive-integrity',
         'archive-verification', 'environment', 'install', 'recovery'}
COUNTS = ('total', 'passed', 'failures', 'errors', 'skips', 'warnings', 'history_skips')
PHASE_STEPS = {
    'source': ('preflight', 'tests', 'kill-gate', 'secret-audit', 'offline-evaluation',
               'assurance-evaluation', 'attack-matrix', 'assurance-mutations',
               'isolated-recovery', 'source-compilation', 'source-package', 'archive-integrity'),
    'fresh-extracted': ('archive-verification', 'environment', 'install', 'tests', 'kill-gate', 'recovery'),
}
HISTORY_TEST = 'test_the_clean_result_is_still_reported_when_history_is_readable'


def test_summary(xml_path=None, output=None):
    summary = dict.fromkeys(COUNTS)
    summary['status'] = 'UNAVAILABLE'
    if xml_path is None:
        summary['status'] = 'NOT RUN'
        return summary
    try:
        root = ET.parse(xml_path).getroot()
        if root.tag not in {'testsuite', 'testsuites'}:
            return summary
        cases = list(root.iter('testcase'))
        if not cases:
            return summary
        counts = dict.fromkeys(COUNTS, 0)
        counts['warnings'] = None  # JUnit does not carry pytest warning totals.
        for case in cases:
            counts['total'] += 1
            outcome = ('errors' if case.find('error') is not None else
                       'failures' if case.find('failure') is not None else
                       'skips' if case.find('skipped') is not None else 'passed')
            counts[outcome] += 1
            if (outcome == 'skips' and case.get('name') == HISTORY_TEST
                and case.get('classname', '').split('.')[-1] == 'test_reproducibility_and_failure_paths'
                and case.find('skipped').get('message') == 'not a clone - the full-history claim cannot be checked here'):
                counts['history_skips'] += 1
        # Refuse truncated/inconsistent XML even when it remains parseable.
        for suite in root.iter('testsuite'):
            if suite.findall('testsuite'):continue
            rows=suite.findall('testcase')
            observed={'tests':len(rows), 'errors':sum(r.find('error') is not None for r in rows),
                      'failures':sum(r.find('failure') is not None for r in rows),
                      'skipped':sum(r.find('skipped') is not None for r in rows)}
            if any(k in suite.attrib and suite.get(k)!=str(v) for k,v in observed.items()):
                return summary
        # Only recognize a pytest numeric terminal-summary line, never emit it.
        # A suppressed/absent warnings summary remains unknown, not a made-up zero.
        if output is not None:
            for line in reversed(output.splitlines()):
                text = line.strip('= ').strip()
                if re.fullmatch(r'\d+ (?:passed|failed|skipped|deselected|xfailed|xpassed|warnings?|errors?)(?:, \d+ (?:passed|failed|skipped|deselected|xfailed|xpassed|warnings?|errors?))* in \d+(?:\.\d+)?s(?: \(.*\))?', text):
                    match = re.search(r'(\d+) warnings?\b', text)
                    counts['warnings'] = int(match.group(1)) if match else 0
                    break
        summary.update(counts, status='AVAILABLE')
    except (OSError, ET.ParseError, ValueError):
        pass  # Explicit UNAVAILABLE counts, never a fabricated passing result.
    return summary


def sanitized(report):
    """Validate both schema and numeric consistency before any persisted/printed data."""
    if not isinstance(report,dict):
        raise ValueError('Invalid evidence object')
    if report.get('phase') not in PHASES or report.get('status') not in STATUSES:
        raise ValueError('Invalid evidence phase/status')
    counts = report['tests']
    if not isinstance(counts,dict):
        raise ValueError('Invalid test evidence object')
    if counts.get('status') not in {'AVAILABLE', 'UNAVAILABLE', 'NOT RUN'}:
        raise ValueError('Invalid test evidence status')
    clean_counts = {'status': counts['status']}
    for key in COUNTS:
        value = counts.get(key)
        if value is not None and (type(value) is not int or not 0 <= value <= 1_000_000_000):
            raise ValueError('Invalid evidence count')
        clean_counts[key] = value
    values = [clean_counts[k] for k in ('total','passed','failures','errors','skips')]
    if counts['status'] == 'AVAILABLE':
        if (any(v is None for v in values) or values[0] != sum(values[1:])
            or clean_counts['history_skips'] is None
            or clean_counts['history_skips'] > clean_counts['skips']):
            raise ValueError('Inconsistent evidence totals')
    elif any(clean_counts[k] is not None for k in COUNTS):
        raise ValueError('Unavailable evidence cannot claim counts')
    steps = []
    for step in report.get('steps', []):
        if not isinstance(step,dict):
            raise ValueError('Invalid evidence step object')
        if step.get('step') not in STEPS or step.get('status') not in STATUSES:
            raise ValueError('Invalid evidence step')
        code = step.get('exit_code')
        if code is not None and (type(code) is not int or not -255 <= code <= 255):
            raise ValueError('Invalid evidence exit code')
        steps.append({'step':step['step'], 'status':step['status'], 'exit_code':code})
    clean = {'format':'threadgate.validation-evidence.v1', 'phase':report['phase'],
             'status':report['status'], 'tests':clean_counts, 'steps':steps}
    for name, length in [('run_id',32), ('expected_sha',40), ('source_commit',40)]:
        value = report.get(name)
        clean[name] = value if isinstance(value,str) and re.fullmatch('[0-9a-f]{'+str(length)+'}',value) else None
    for name in ('workflow_run_id','workflow_attempt'):
        value=report.get(name)
        clean[name]=value if isinstance(value,str) and re.fullmatch(r'[0-9]{1,32}',value) else None
    version=report.get('python')
    clean['python']=version if isinstance(version,str) and re.fullmatch(r'\d{1,3}\.\d{1,3}\.\d{1,3}',version) else None
    return clean


def checkout_identity(root):
    """Observe actual Git HEAD and cleanliness, not a report's expected_sha claim."""
    try:
        top=subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=root,text=True,stderr=subprocess.DEVNULL).strip()
        if Path(top).resolve()!=Path(root).resolve():return None
        sha=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True,stderr=subprocess.DEVNULL).strip()
        dirty=subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True,stderr=subprocess.DEVNULL).strip()
        return sha if not dirty and re.fullmatch('[0-9a-f]{40}',sha) else None
    except (OSError,subprocess.CalledProcessError):
        return None


def invocation(root, run_id):
    context={'run_id':run_id,'expected_sha':os.getenv('EXPECTED_SHA'),
             'source_commit':checkout_identity(root),
             'workflow_run_id':os.getenv('GITHUB_RUN_ID'),
             'workflow_attempt':os.getenv('GITHUB_RUN_ATTEMPT')}
    if (not re.fullmatch('[0-9a-f]{32}',run_id) or context['source_commit'] is None
        or context['source_commit']!=context['expected_sha']):
        raise ValueError('Checkout identity prerequisite failed')
    if os.getenv('GITHUB_ACTIONS')=='true' and any(
        not isinstance(context[k],str) or not re.fullmatch(r'[0-9]{1,32}',context[k])
        for k in ('workflow_run_id','workflow_attempt')):
        raise ValueError('Workflow identity prerequisite failed')
    return context


def evidence_path(root, phase):
    if phase not in PHASES:raise ValueError('Invalid evidence phase')
    return Path(root)/'data/runs/ci-evidence'/f'{phase}.json'


def invalidate_evidence(root, phase):
    # Only this helper's disposable per-phase output, never release/prior deliverables.
    path=evidence_path(root,phase)
    path.unlink(missing_ok=True)
    path.with_suffix('.json.pending').unlink(missing_ok=True)


def validate_test_outcomes(tests, phase):
    # Warnings are optional diagnostics, not invented zeroes or an acceptance gate.
    if (tests['status']!='AVAILABLE' or tests['total']<=0 or tests['passed']<=0
        or tests['failures'] or tests['errors']):
        raise ValueError('Required test outcomes unavailable or unsuccessful')
    # Only the already-documented no-Git history diagnostic may skip in an export.
    allowed=tests['history_skips'] if phase=='fresh-extracted' else 0
    if tests['skips']!=allowed or allowed>1:
        raise ValueError('Required test was skipped')


def validate_mandatory(report, phase, context):
    if not isinstance(report,dict) or report.get('format')!='threadgate.validation-evidence.v1':
        raise ValueError('Invalid evidence format')
    clean=sanitized(report)
    if clean['phase']!=phase or any(clean[k]!=v for k,v in context.items()):
        raise ValueError('Evidence commit or invocation mismatch')
    if clean['status']!='PASS':raise ValueError('Required phase did not pass')
    if tuple(s['step'] for s in clean['steps'])!=PHASE_STEPS[phase] or any(
        s['status']!='PASS' or s['exit_code']!=0 for s in clean['steps']):
        raise ValueError('Mandatory checks absent or unsuccessful')
    validate_test_outcomes(clean['tests'],phase)
    return clean


def write_evidence(root, phase, status, tests, steps):
    report = sanitized({'phase':phase, 'status':status, 'tests':tests, 'steps':steps,
        'run_id':os.getenv('THREADGATE_EVIDENCE_RUN_ID'), 'expected_sha':os.getenv('EXPECTED_SHA'),
        'source_commit':checkout_identity(root), 'workflow_run_id':os.getenv('GITHUB_RUN_ID'),
        'workflow_attempt':os.getenv('GITHUB_RUN_ATTEMPT')})
    report['python'] = '.'.join(map(str,sys.version_info[:3]))
    path = evidence_path(root,phase)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.json.pending')
    temporary.write_text(json.dumps(report,sort_keys=True)+'\n')
    temporary.replace(path)
    return report
