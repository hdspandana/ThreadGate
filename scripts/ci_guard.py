"""Fail-closed CI identity/capacity/privacy checks; no credentials or raw logs emitted."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import json
import uuid
ROOT=Path(__file__).resolve().parents[1]
GIB=1024**3


def git(*args):
    return subprocess.check_output(['git',*args],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()


def check_identity(expected):
    if len(expected)!=40 or any(c not in '0123456789abcdef' for c in expected):
        raise ValueError('Expected event SHA is invalid')
    if git('rev-parse','HEAD')!=expected:
        raise ValueError('Checkout does not match expected event SHA')
    if git('status','--porcelain'):
        raise ValueError('Checkout is not clean')


def capacity(minimum):
    for path in (ROOT,Path(os.getenv('RUNNER_TEMP',tempfile.gettempdir()))):
        free=shutil.disk_usage(path).free
        print('Runner filesystem available bytes:',free,'required:',minimum,flush=True)
        if free<minimum:raise ValueError('Insufficient runner filesystem capacity')
    print('Filesystem check does NOT verify account artifact quota.',flush=True)


def private_history():
    paths=git('log','--all','--format=','--name-only').splitlines()
    return any('COORDINATOR-ONLY' in p or 'reviewer-responses' in p or 'private-labels' in p for p in paths)


def preflight():
    check_identity(os.environ.get('EXPECTED_SHA',''))
    if os.getenv('REPOSITORY_PRIVATE')!='true' and private_history():
        raise ValueError('Public validation blocked: private review material in reachable history; owner-approved private route required')
    try:
        from scripts.package_release import check_docker_context
    except ModuleNotFoundError:
        from package_release import check_docker_context
    check_docker_context(ROOT)
    capacity(8*GIB)
    print('Runner OS:',os.getenv('RUNNER_OS','unknown'),'architecture:',os.getenv('RUNNER_ARCH','unknown'))
    print('Python:',sys.version.split()[0],'event SHA:',git('rev-parse','HEAD'))
    print('OS release:',Path('/etc/os-release').read_text() if Path('/etc/os-release').exists() else 'unavailable')


def run(command):
    # Optional commands need no test report; these two phases require evidence.
    if not command:raise ValueError('Missing command')
    phase=('source' if any(Path(arg).name=='release_check.py' for arg in command) else
           'fresh-extracted' if any(Path(arg).name=='ci_guard.py' for arg in command) and command[-1]=='fresh' else None)
    run_id=uuid.uuid4().hex
    env=dict(os.environ,THREADGATE_EVIDENCE_RUN_ID=run_id)
    if phase:
        try:
            from scripts import validation_evidence as evidence
        except ModuleNotFoundError:
            import validation_evidence as evidence
        evidence.invalidate_evidence(ROOT,phase)
        try:context=evidence.invocation(ROOT,run_id)
        except ValueError:
            print('CI evidence FAIL:',phase,'checkout/workflow identity prerequisite')
            return 1
    with tempfile.TemporaryFile() as output:
        result=subprocess.run(command,cwd=ROOT,env=env,stdout=output,stderr=subprocess.STDOUT)
    print('CI command exit:',result.returncode,flush=True)
    if phase:
        try:
            report=json.loads(evidence.evidence_path(ROOT,phase).read_text())
            if result.returncode!=0:raise ValueError('Command failed')
            if evidence.invocation(ROOT,run_id)!=context:raise ValueError('Checkout changed')
            report=evidence.validate_mandatory(report,phase,context)
        except (OSError,ValueError,KeyError,TypeError):
            print('CI evidence FAIL:',phase,'mandatory report/outcomes invalid or unavailable')
            return result.returncode or 1
        print('CI evidence:',json.dumps(report,sort_keys=True),flush=True)
    return result.returncode


def fresh():
    # Called only after source gate/browser/container success. No second ZIP build.
    import zipfile
    try:
        from scripts.validation_evidence import test_summary, write_evidence, invalidate_evidence, validate_test_outcomes
    except ModuleNotFoundError:
        from validation_evidence import test_summary, write_evidence, invalidate_evidence, validate_test_outcomes
    invalidate_evidence(ROOT,'fresh-extracted')
    steps=[];counts=test_summary();status='FAIL'

    def checked(name, command, cwd=None, xml=None):
        nonlocal counts
        # Even direct invocation must not emit pip/test/provider exception text.
        result=subprocess.run(command,cwd=cwd,capture_output=True,text=True)
        steps.append({'step':name,'status':'PASS' if result.returncode==0 else 'FAIL',
                      'exit_code':result.returncode})
        if xml is not None:
            counts=test_summary(xml,result.stdout+result.stderr)
            if result.returncode==0:
                try:validate_test_outcomes(counts,'fresh-extracted')
                except ValueError:
                    steps[-1]['status']='FAIL'
                    raise
        result.check_returncode()

    try:
        capacity(8*GIB)
        archive=ROOT/'release/ThreadGate-TeamWorkspace.zip'
        manifest=json.loads((ROOT/'release/TeamWorkspace-manifest.json').read_text())
        if manifest['source_identity']['source_commit']!=os.environ.get('EXPECTED_SHA'):
            raise ValueError('Release identity differs from expected event SHA')
        # The verifier rejects unsafe paths and verifies every blob before extraction.
        checked('archive-verification',[sys.executable,str(ROOT/'scripts/verify_release.py'),'--require-commit'])
        with tempfile.TemporaryDirectory(prefix='threadgate-extracted-',dir=os.getenv('RUNNER_TEMP')) as folder:
            dest=Path(folder)
            with zipfile.ZipFile(archive) as z:z.extractall(dest)
            source=dest/'ThreadGate';venv=dest/'runtime'
            checked('environment',[sys.executable,'-m','venv',str(venv)])
            python=venv/'bin/python'
            checked('install',[str(python),'-m','pip','install','--no-cache-dir','-r',str(source/'requirements.lock')])
            xml=dest/'fresh-tests.xml'
            checked('tests',[str(python),'-m','pytest','-o','addopts=','-q','-r','s',
                             '--junitxml',str(xml)],cwd=source,xml=xml)
            for name,script in (('kill-gate','kill_gate.py'),('recovery','recovery_check.py')):
                checked(name,[str(python),str(source/'scripts'/script)],cwd=source)
        validate_test_outcomes(counts,'fresh-extracted')
        status='PASS'
    finally:
        write_evidence(ROOT,'fresh-extracted',status,counts,steps)
    print('Fresh extracted install/tests passed; no-Git history limitation retained.')


def docker_build(command):
    """Approved CI build entrypoint; reject alternate contexts/options before Docker."""
    if command!=['-t','threadgate:ci','.']:
        raise ValueError('Unapproved Docker build options or context')
    try:
        from scripts.distribution_policy import check_docker_context
    except ModuleNotFoundError:
        from distribution_policy import check_docker_context
    check_docker_context(ROOT)
    result=subprocess.run(['docker','build',*command],cwd=ROOT,capture_output=True)
    print('Docker build exit:',result.returncode)  # No raw build/auth diagnostics.
    return result.returncode


def main():
    p=argparse.ArgumentParser();p.add_argument('operation',choices=('preflight','capacity','run','fresh','docker-build'));p.add_argument('command',nargs=argparse.REMAINDER)
    a=p.parse_args()
    try:
        if a.operation=='preflight':preflight()
        elif a.operation=='capacity':capacity(8*GIB)
        elif a.operation=='fresh':fresh()
        elif a.operation=='docker-build':return docker_build(a.command)
        else:return run(a.command)
    except ValueError as exc:
        print('CI guard FAIL:',str(exc))
        return 1
    except Exception:
        # No exception text: private paths/model output can occur in exceptions.
        print('CI guard FAIL: identity, privacy, capacity or validation prerequisite unmet; no artifact approved.')
        return 1
    return 0


if __name__=='__main__':raise SystemExit(main())
