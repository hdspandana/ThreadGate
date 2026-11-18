"""Isolated release/provenance and recovery regressions; no production files."""
import importlib.util
import json
from pathlib import Path
import subprocess
import zipfile
import pytest
ROOT=Path(__file__).resolve().parents[1]


def script(name):
    spec=importlib.util.spec_from_file_location('workflow_'+name,ROOT/'scripts'/f'{name}.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


@pytest.fixture
def package(tmp_path,monkeypatch):
    def git(*args):return subprocess.run(['git',*args],cwd=tmp_path,check=True,capture_output=True)
    git('init','-q')
    (tmp_path/'app').mkdir()
    (tmp_path/'app/main.py').write_text('print("synthetic")\n')
    (tmp_path/'README.md').write_text('Synthetic release fixture\n')
    (tmp_path/'.gitignore').write_text('release/\napp/privatefixture.json\n')
    git('add','README.md','app/main.py','.gitignore')
    git('-c','user.name=ThreadGate Test','-c','user.email=test@example.invalid','commit','-qm','Synthetic fixture')
    (tmp_path/'app/privatefixture.json').write_text('synthetic private data must never hitchhike')
    packager=script('package_release');monkeypatch.setattr(packager,'ROOT',tmp_path)
    packager.main(['--require-clean'])
    return tmp_path,packager


def test_clean_package_excludes_ignored_private_files_and_matches_commit(package):
    root,packager=package
    assert packager.included(root/'.gitattributes') is False  # absent files are never included
    (root/'.gitattributes').write_text('* text=auto eol=lf\n')
    assert packager.included(root/'.gitattributes')  # config belongs in future packages
    (root/'.gitattributes').unlink()
    report=script('verify_release').verify(root/'release/ThreadGate-TeamWorkspace.zip',root/'release/TeamWorkspace-manifest.json',root,True)
    assert report['status']=='PASS' and report['committed_entries_matched']==3
    with zipfile.ZipFile(root/'release/ThreadGate-TeamWorkspace.zip') as z:
        assert not any('privatefixture' in name for name in z.namelist())


def test_commit_packages_are_reproducible(package):
    root,packager=package;path=root/'release/ThreadGate-TeamWorkspace.zip';before=path.read_bytes()
    packager.main(['--require-clean']);assert path.read_bytes()==before


@pytest.mark.parametrize('kind',['archive','manifest-entry','manifest-identity','size'])
def test_archive_verifier_rejects_tampered_evidence(package,kind):
    root,_=package;archive=root/'release/ThreadGate-TeamWorkspace.zip';manifest=root/'release/TeamWorkspace-manifest.json'
    value=json.loads(manifest.read_text())
    if kind=='archive':archive.write_bytes(archive.read_bytes()+b'corruption')
    elif kind=='manifest-entry':value['files'][0]['sha256']='0'*64
    elif kind=='size':value['compressed_bytes']+=1
    else:value['source_identity']['source_commit']='0'*40
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError):script('verify_release').verify(archive,manifest)


def test_integrity_check_without_git_does_not_claim_commit_verification(package):
    root,_=package
    report=script('verify_release').verify(root/'release/ThreadGate-TeamWorkspace.zip',root/'release/TeamWorkspace-manifest.json')
    assert report['commit_correspondence']=='NOT RUN' and report['committed_entries_matched']==0


def test_dirty_source_cannot_be_a_commit_release(package):
    root,packager=package;(root/'app/main.py').write_text('changed\n')
    with pytest.raises(SystemExit):packager.main(['--require-clean'])


def test_synthetic_recovery_retention_mfa_and_replay_integrity():
    report=script('recovery_check').exercise(False)
    assert report['status']=='PASS' and report['provider_calls']==0 and report['private_files_retained'] is False
    assert len(report['checks'])>=18 and all(c['status']=='PASS' for c in report['checks'])
    assert report['browser']=='NOT RUN'


def test_backup_refuses_corrupted_audit_without_changing_source(tmp_path):
    import sqlite3
    import secrets
    from threadgate.workspace import Workspace
    service=Workspace(tmp_path/'source.db')
    service.bootstrap('synthetic-owner',secrets.token_urlsafe(32))
    with sqlite3.connect(service.path) as db:db.execute("UPDATE audit SET actor='synthetic-forgery'")
    before=Path(service.path).read_bytes();target=tmp_path/'private.backup'
    result=subprocess.run([__import__('sys').executable,str(ROOT/'scripts/backup_workspace.py'),
        '--db',service.path,'--output',str(target)],capture_output=True,text=True,timeout=20)
    assert result.returncode==1 and not target.exists()
    assert Path(service.path).read_bytes()==before
    assert 'Traceback' not in result.stderr
