"""Verify archive/manifest and optionally byte-match the declared Git commit.

The manifest/hash is unsigned, not an external authenticity anchor. Does not
extract files. --require-commit requires readable Git history at --source-root.
"""
import argparse
import hashlib
import json
from pathlib import Path,PurePosixPath
import stat
import subprocess
import zipfile
ROOT=Path(__file__).resolve().parents[1]
LIMIT=128_000_000
try:
    from scripts.distribution_policy import allowed
except ModuleNotFoundError:
    from distribution_policy import allowed


def verify(archive,manifest,source_root=None,require_commit=False):
    archive=Path(archive);manifest=json.loads(Path(manifest).read_text())
    if archive.stat().st_size!=manifest['compressed_bytes']:raise ValueError('Compressed size mismatch')
    if not 0<archive.stat().st_size<LIMIT:raise ValueError('Archive size')
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=manifest['archive_sha256']:raise ValueError('Archive digest')
    expected={r['path']:r for r in manifest['files']}
    if len(expected)!=len(manifest['files']):raise ValueError('Duplicate manifest entry')
    with zipfile.ZipFile(archive) as z:
        infos=z.infolist();names=[i.filename for i in infos]
        if len(names)!=len(set(names)) or len(names)!=manifest['file_count']:raise ValueError('Archive entries')
        total=sum(i.file_size for i in infos)
        if not 0<total<LIMIT or total!=manifest['uncompressed_bytes']:raise ValueError('Uncompressed size')
        actual={}
        for info in infos:
            path=PurePosixPath(info.filename)
            if ('\\' in info.filename or path.is_absolute() or '..' in path.parts or
                not info.filename.startswith('ThreadGate/') or info.is_dir() or stat.S_ISLNK(info.external_attr>>16)):
                raise ValueError('Unsafe archive path')
            rel=info.filename[len('ThreadGate/'):]
            if rel!='RELEASE_IDENTITY.json' and not allowed(rel):
                raise ValueError('Excluded distribution path')
            payload=z.read(info)
            if rel not in expected or len(payload)!=expected[rel]['bytes'] or hashlib.sha256(payload).hexdigest()!=expected[rel]['sha256']:
                raise ValueError('Entry content mismatch')
            actual[rel]=payload
        if set(actual)!=set(expected):raise ValueError('Missing manifest entry')
        if 'Dockerfile' in actual:
            try:
                from scripts.package_release import validate_docker_policy
            except ModuleNotFoundError:
                from package_release import validate_docker_policy
            if 'Dockerfile.dockerignore' in actual:
                raise ValueError('Unreviewed Docker-specific ignore override')
            validate_docker_policy(actual.get('.dockerignore',b'').decode('utf-8'))
        identity=json.loads(actual['RELEASE_IDENTITY.json'])
        if identity!=manifest['source_identity']:raise ValueError('Identity mismatch')
    matched=0
    if require_commit:
        root=Path(source_root or ROOT).resolve()
        top=subprocess.check_output(['git','rev-parse','--show-toplevel'],cwd=root,stderr=subprocess.DEVNULL,text=True).strip()
        if Path(top).resolve()!=root:raise ValueError('Not the intended Git source root')
        commit=identity.get('source_commit')
        if not commit or identity.get('source_tree_clean') is not True:raise ValueError('Not a clean commit release')

        for rel, payload in actual.items():
            if rel == 'RELEASE_IDENTITY.json':
                continue

            committed_blob = subprocess.check_output(
                ['git', 'rev-parse', f'{commit}:{rel}'],
                cwd=root,
                stderr=subprocess.DEVNULL,
                text=True
            ).strip()

            archive_blob = subprocess.check_output(
                ['git', 'hash-object', '--path', rel, '--stdin'],
                cwd=root,
                input=payload
            ).decode().strip()

            if archive_blob != committed_blob:
                raise ValueError('Commit content mismatch')

            matched += 1

    return {'status':'PASS','archive_entries':len(actual),'compressed_bytes':archive.stat().st_size,
            'uncompressed_bytes':total,'source_identity':identity,
            'commit_correspondence':'PASS' if require_commit else 'NOT RUN',
            'committed_entries_matched':matched,'trust':'Unsigned manifest; independent expected hash or signature required for authenticity.'}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive',default=str(ROOT/'release/ThreadGate-TeamWorkspace.zip'))
    parser.add_argument('--manifest',default=str(ROOT/'release/TeamWorkspace-manifest.json'))
    parser.add_argument('--source-root',default=str(ROOT))
    parser.add_argument('--require-commit',action='store_true')
    args=parser.parse_args(argv)
    try:report=verify(args.archive,args.manifest,args.source_root,args.require_commit)
    except Exception as exc:
        report={'status':'FAIL','error_type':type(exc).__name__,'message':'Archive/manifest validation failed; no verified artifact claimed.'}
    print(json.dumps(report,indent=2));return 0 if report['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
