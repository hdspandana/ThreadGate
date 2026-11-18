"""Create a source-only release, strictly below 128 MB compressed and unpacked."""
from __future__ import annotations
import hashlib
import os
import argparse
import subprocess
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 128_000_000  # decimal MB: stricter than 128 MiB
try:
    from scripts.distribution_policy import allowed, check_docker_context, validate_docker_policy as validate_docker_policy
except ModuleNotFoundError:
    from distribution_policy import allowed, check_docker_context, validate_docker_policy as validate_docker_policy


def included(path):
    rel = path.relative_to(ROOT)
    if not allowed(rel):return False
    if path.is_symlink():raise ValueError('Symlink not allowed in distribution')
    return path.is_file()


def source_identity():
    try:
        def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True,stderr=subprocess.DEVNULL).strip()
        if Path(git('rev-parse','--show-toplevel')).resolve()!=ROOT.resolve():raise ValueError('Not this source tree')
        clean=not bool(git('status','--porcelain','--untracked-files=all'))
        return {'source_commit':git('rev-parse','HEAD'),'branch':git('branch','--show-current'),
                'source_tree_clean':clean,'source_state':'commit' if clean else 'uncommitted-not-a-commit-release'}
    except (OSError,ValueError,subprocess.CalledProcessError):
        return {'source_commit':None,'branch':None,'source_tree_clean':None,'source_state':'no-git-history'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-clean',action='store_true')
    args=parser.parse_args(argv)
    if os.getenv('GITHUB_ACTIONS')=='true' and os.getenv('GITHUB_WORKSPACE')==str(ROOT):
        from ci_guard import capacity,GIB
        capacity(8*GIB)
    check_docker_context(ROOT)
    identity=source_identity()
    if args.require_clean and identity['source_tree_clean'] is not True:
        raise SystemExit('A clean committed source worktree is required; no commit release was created.')

    files = sorted(p for p in ROOT.rglob('*') if included(p))
    identity_payload = (json.dumps(identity, indent=2, sort_keys=True) + '\n').encode()

    if identity['source_tree_clean'] is True:
        # Ignored private files must never hitchhike in a clean commit release.
        tracked = set(
            subprocess.check_output(
                ['git', 'ls-files', '-z'], cwd=ROOT
            ).decode().split('\0')
        )
        files = [
            p for p in files
            if p.relative_to(ROOT).as_posix() in tracked
        ]

    total = sum(p.stat().st_size for p in files) + len(identity_payload)
    if total >= LIMIT:
        raise SystemExit('Uncompressed source exceeds 128 MB limit')

    dest = ROOT / 'release'
    dest.mkdir(exist_ok=True)
    archive = dest / 'ThreadGate-TeamWorkspace.zip'
    entries = []

    payloads = [
        (p.relative_to(ROOT).as_posix(), p.read_bytes())
        for p in files
    ]

    if identity['source_tree_clean'] is True:
        for rel, payload in payloads:
            committed_blob = subprocess.check_output(
                ['git', 'rev-parse', f"{identity['source_commit']}:{rel}"],
                cwd=ROOT,
                text=True
            ).strip()

            working_blob = subprocess.check_output(
                ['git', 'hash-object', '--path', rel, '--stdin'],
                cwd=ROOT,
                input=payload
            ).decode().strip()

            if working_blob != committed_blob:
                raise SystemExit(
                    'Source changed during packaging; no commit release claimed.'
                )

    payloads.append(('RELEASE_IDENTITY.json',identity_payload))
    payloads.sort(key=lambda item:item[0])
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel,payload in payloads:
            info = zipfile.ZipInfo('ThreadGate/' + rel, date_time=(2026, 10, 24, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            z.writestr(info, payload)
            entries.append({'path': rel, 'bytes':len(payload),
                            'sha256':hashlib.sha256(payload).hexdigest()})
    size = archive.stat().st_size
    if size >= LIMIT:
        archive.unlink()
        raise SystemExit('Compressed archive exceeds 128 MB limit')
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert sum(i.file_size for i in z.infolist()) == total
    manifest = {'archive':archive.name, 'limit_bytes':LIMIT, 'compressed_bytes':size,
                'uncompressed_bytes':total, 'file_count':len(payloads), 'source_identity':identity,
                'archive_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(), 'files':entries}
    (dest / 'TeamWorkspace-manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps({k:v for k,v in manifest.items() if k != 'files'}, indent=2))


if __name__ == '__main__':
    main()
