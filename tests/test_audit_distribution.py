"""Check distribution deny rules without archives, private contents or Docker."""
import ast
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]


def load(name):
    spec=importlib.util.spec_from_file_location('audit_distribution_'+name,ROOT/'scripts'/f'{name}.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def test_actual_docker_context_policy():
    package=load('package_release')
    package.check_docker_context(ROOT)
    # Ensure both CI preflight and packaging actually invoke the guard.
    for script,function in [('ci_guard','preflight'),('package_release','main')]:
        module=ast.parse((ROOT/'scripts'/f'{script}.py').read_text())
        function=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name==function)
        assert any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='check_docker_context' for n in ast.walk(function))


@pytest.mark.parametrize('remove',['**/COORDINATOR-ONLY*','**/reviewer-responses','**/private-labels'])
def test_context_without_required_recursive_exclusion_rejected(remove):
    policy=(ROOT/'.dockerignore').read_text().replace(remove,'')
    with pytest.raises(ValueError):load('package_release').validate_docker_policy(policy)


@pytest.mark.parametrize('exception',['!**/COORDINATOR-ONLY*','!docs/**','!**/private-labels/**'])
def test_later_reinclusion_rejected(exception):
    with pytest.raises(ValueError):
        load('package_release').validate_docker_policy((ROOT/'.dockerignore').read_text()+'\n'+exception+'\n')


def test_docker_specific_override_rejected(tmp_path):
    (tmp_path/'Dockerfile').write_text('COPY . .\n')
    (tmp_path/'.dockerignore').write_text((ROOT/'.dockerignore').read_text())
    (tmp_path/'Dockerfile.dockerignore').write_text('')
    with pytest.raises(ValueError):load('package_release').check_docker_context(tmp_path)


@pytest.mark.parametrize('rel',['COORDINATOR-ONLY.json','docs/deep/COORDINATOR-ONLY-map.json',
    'docs/COORDINATOR-ONLY-directory/item.json','data/private-labels/item.json',
    'docs/reviewer-responses/item.json'])
def test_private_review_paths_denied_by_package_and_verifier(rel):
    package=load('package_release')
    # Exclusion happens before touching contents or requiring the file to exist.
    assert not package.included(ROOT/rel)
    module=ast.parse((ROOT/'scripts/verify_release.py').read_text())
    guard=next(n for n in ast.walk(module) if isinstance(n,ast.If)
               and any(isinstance(c,ast.Constant) and c.value=='Excluded distribution path' for c in ast.walk(n)))
    namespace={'rel':rel,'allowed':__import__('scripts.distribution_policy',fromlist=['allowed']).allowed}
    # Execute the actual verifier's path rejection, not a duplicate predicate.
    with pytest.raises(ValueError):
        exec(compile(ast.Module(body=[guard],type_ignores=[]),'<actual-verifier-guard>','exec'),namespace)


@pytest.mark.parametrize('kind',['valid','missing-ignore','missing-exclusion','reinclusion','override'])
def test_archive_docker_recipe_validation_without_archive(kind):
    policy=(ROOT/'.dockerignore').read_text()
    actual={'Dockerfile':b'COPY . .\n','.dockerignore':policy.encode()}
    if kind=='missing-ignore':actual.pop('.dockerignore')
    elif kind=='missing-exclusion':actual['.dockerignore']=policy.replace('**/private-labels','').encode()
    elif kind=='reinclusion':actual['.dockerignore']=(policy+'\n!docs/**\n').encode()
    elif kind=='override':actual['Dockerfile.dockerignore']=b''
    module=ast.parse((ROOT/'scripts/verify_release.py').read_text())
    guard=next(n for n in ast.walk(module) if isinstance(n,ast.If)
               and ast.unparse(n.test)=="'Dockerfile' in actual")
    code=compile(ast.Module(body=[guard],type_ignores=[]),'<actual-verifier-docker-policy>','exec')
    if kind=='valid':exec(code,{'actual':actual})
    else:
        with pytest.raises(ValueError):exec(code,{'actual':actual})


@pytest.mark.parametrize('rel',[
    'app/product.py','src/threadgate/tokens.py','src/threadgate/workspace.py',
    'tests/test_workspace.py','scripts/release_check.py','requirements.lock',
    'requirements.txt','.env.example','.streamlit/config.toml','Dockerfile',
    'data/cases/frozen_v1.json','data/records/vendor_master.json',
    'data/assurance/manifest.json','docs/CI_HARDENING.md','deployment/Caddyfile',
])
def test_required_application_paths_remain_allowed(rel):
    from scripts.distribution_policy import allowed
    assert allowed(rel)
    if (ROOT/rel).is_file():assert load('package_release').included(ROOT/rel)


PROHIBITED = [
    'docs/deep/COORDINATOR-ONLY-map.json','docs/reviewer-responses/reply.json',
    'data/private-labels/item.json','app/.env','app/.env.production','src/secrets.toml',
    'deployment/key.pem','app/credential.key','app/credentials.json','app/tokens.json',
    'app/.netrc','app/id_rsa','app/.venv/lib/thing.py','src/venv/lib/thing.py',
    'app/.cache/data','src/__pycache__/thing.pyc','.git/objects/x',
    'app/.git/config','data/runs/private.db','app/runtime.sqlite3-wal',
    'docs/old.zip','docs/nested.ZiP','app/backup.tar.gz','docs/old.backup',
    'app/logs/private.txt','docs/ThreadGate-old/app.py','snapshots/workspace.txt',
    'app/snapshots/old.py','data/raw/unapproved.json','unknown-root/stale.txt',
    'app/Otherfile.dockerignore','src/.env.example','app/.docker/config.json','app/.ssh/key',
    'app/.aws/credentials','app/.config/gcloud/auth.json','app/.npmrc',
]


@pytest.mark.parametrize('rel', PROHIBITED)
def test_complete_policy_is_shared_by_package_verifier_and_docker_rules(rel):
    from fnmatch import fnmatchcase
    from pathlib import PurePosixPath
    from scripts.distribution_policy import allowed, DENY
    assert not allowed(rel)
    assert not load('package_release').included(ROOT/rel)
    # Canonical recursive deny rules cover prohibited names under allowed roots;
    # unknown root/data directories are denied by the default-deny context rule.
    parts=PurePosixPath(rel).parts
    assert (any(part.startswith('.env') or any(fnmatchcase(part,p) for p in DENY) for part in parts)
            or parts[0] not in {'app','src','docs','deployment'} )
    verifier=load('verify_release')
    assert verifier.allowed is allowed


@pytest.mark.parametrize('removed',['**/.git','**/.venv','**/.env.*','**/credentials.*',
                                    '**/token.json','**/runs','**/*.[zZ][iI][pP]'])
def test_each_mandatory_policy_rule_cannot_be_removed(removed):
    from scripts.distribution_policy import validate_docker_policy
    policy=(ROOT/'.dockerignore').read_text()
    assert removed in policy.splitlines()
    with pytest.raises(ValueError):validate_docker_policy(policy.replace(removed+'\n',''))


@pytest.mark.parametrize('options',[
    {'context':'../elsewhere'}, {'dockerfile':'deployment/Alternate.Dockerfile'},
    {'additional_contexts':{'private':'../private'}},
])
def test_alternate_context_options_are_rejected(options):
    from scripts.distribution_policy import check_docker_context
    with pytest.raises(ValueError):check_docker_context(ROOT,**options)


@pytest.mark.parametrize('build', ['build:\n      context: ../private',
    'build:\n      dockerfile: Otherfile','build:\n      additional_contexts: {private: ../private}'])
def test_compose_context_override_rejected(tmp_path,build):
    from scripts.distribution_policy import check_docker_context
    (tmp_path/'Dockerfile').write_text('COPY . .\n')
    (tmp_path/'.dockerignore').write_text((ROOT/'.dockerignore').read_text())
    (tmp_path/'compose.yaml').write_text('services:\n  app:\n    '+build+'\n')
    with pytest.raises(ValueError):check_docker_context(tmp_path)


def test_ci_docker_entrypoint_enforces_policy_before_build(monkeypatch):
    import subprocess
    guard=load('ci_guard');calls=[]
    monkeypatch.setattr(guard.subprocess,'run',lambda command,**kw:
        calls.append(command) or subprocess.CompletedProcess(command,0))
    for command in (['-f','Otherfile','.'],['--build-context','private=../private','.'],['-t','threadgate:ci','..']):
        with pytest.raises(ValueError):guard.docker_build(command)
    assert calls==[]
    assert guard.docker_build(['-t','threadgate:ci','.'])==0
    assert calls==[['docker','build','-t','threadgate:ci','.']]


def test_allowed_symlink_is_rejected_by_both_context_and_packager(tmp_path,monkeypatch):
    from scripts.distribution_policy import check_docker_context
    (tmp_path/'Dockerfile').write_text('COPY . .\n')
    (tmp_path/'.dockerignore').write_text((ROOT/'.dockerignore').read_text())
    (tmp_path/'app').mkdir()
    link=tmp_path/'app/link.py';link.symlink_to('../private.pem')
    with pytest.raises(ValueError):check_docker_context(tmp_path)
    package=load('package_release');monkeypatch.setattr(package,'ROOT',tmp_path)
    with pytest.raises(ValueError):package.included(link)


@pytest.mark.parametrize('name',['compose.override.yaml','docker-compose.yml'])
def test_automatic_compose_override_is_not_silent(tmp_path,name):
    from scripts.distribution_policy import check_docker_context
    (tmp_path/'Dockerfile').write_text('COPY . .\n')
    (tmp_path/'.dockerignore').write_text((ROOT/'.dockerignore').read_text())
    (tmp_path/name).write_text('services: {}\n')
    with pytest.raises(ValueError):check_docker_context(tmp_path)


def test_docker_cli_parser_uses_guarded_entrypoint(monkeypatch):
    import sys
    guard=load('ci_guard');seen=[]
    monkeypatch.setattr(guard,'docker_build',lambda command:seen.append(command) or 0)
    monkeypatch.setattr(sys,'argv',['ci_guard.py','docker-build','-t','threadgate:ci','.'])
    assert guard.main()==0
    assert seen==[['-t','threadgate:ci','.']]


@pytest.mark.parametrize('configuration',[
    'services: {app: {build: ../private}}',
    'x-build: &private\n  build: ../private\nservices:\n  app:\n    <<: *private',
    'services:\n  app:\n    "buil\\u0064": ../private',
    'services:\n  app:\n    !!str build: ../private',
])
def test_unsupported_yaml_forms_cannot_hide_context_overrides(tmp_path,configuration):
    from scripts.distribution_policy import check_docker_context
    (tmp_path/'Dockerfile').write_text('COPY . .\n')
    (tmp_path/'.dockerignore').write_text((ROOT/'.dockerignore').read_text())
    (tmp_path/'compose.yaml').write_text(configuration+'\n')
    with pytest.raises(ValueError):check_docker_context(tmp_path)


@pytest.mark.parametrize('tagged',[
    '!reviewed build: ../private',
    '!reviewed build: .',
    'build: !reviewed ../private',
    '!!str build: ../private',
    '!<tag:example.org,2026:reviewed> build: ../private',
])
def test_parser_rejects_actual_yaml_tags_in_compose(tmp_path,tagged):
    from scripts.distribution_policy import check_docker_context
    (tmp_path/'Dockerfile').write_text('COPY . .\n')
    (tmp_path/'.dockerignore').write_text((ROOT/'.dockerignore').read_text())
    (tmp_path/'compose.yaml').write_text('services:\n  app:\n    '+tagged+'\n')
    with pytest.raises(ValueError,match='Unsupported Compose override syntax'):
        check_docker_context(tmp_path)


def test_tag_lookalikes_in_quotes_and_comments_are_not_tags():
    from scripts.distribution_policy import validate_compose_policy
    validate_compose_policy('''services:
  app:
    build: .
    # !reviewed build: ../private !!str !<tag:example.org,2026:reviewed>
    command: "echo !reviewed build: ../private !!str"
    labels:
      note: '!<tag:example.org,2026:reviewed> # &anchor *alias {text}'
''')


def test_parser_dependency_is_declared_and_bootstrapped_before_every_preflight():
    import yaml
    pin='PyYAML==6.0.3'
    assert pin in (ROOT/'requirements.lock').read_text().splitlines()
    assert 'PyYAML>=6.0.3,<7' in (ROOT/'requirements.txt').read_text().splitlines()
    workflow=yaml.safe_load((ROOT/'.github/workflows/verify.yml').read_text())
    for job in workflow['jobs'].values():
        steps=job['steps']
        setup=next(i for i,s in enumerate(steps) if s.get('uses','').startswith('actions/setup-python@'))
        capacity=next(i for i,s in enumerate(steps) if s.get('run')=='python -B scripts/ci_guard.py capacity')
        bootstrap=next(i for i,s in enumerate(steps) if s.get('run')==
            f'python -B scripts/ci_guard.py run python -m pip install --no-cache-dir --no-deps {pin}')
        preflight=next(i for i,s in enumerate(steps) if s.get('run')=='python3 -B scripts/ci_guard.py preflight')
        assert setup<capacity<bootstrap<preflight
        assert all('continue-on-error' not in steps[i] and 'if' not in steps[i]
                   for i in (setup,capacity,bootstrap,preflight))


def test_missing_yaml_parser_fails_closed(monkeypatch):
    import sys
    from scripts.distribution_policy import validate_compose_policy
    monkeypatch.setitem(sys.modules,'yaml',None)
    with pytest.raises(ValueError,match='declared PyYAML dependency'):
        validate_compose_policy('services:\n  app:\n    build: .\n')


@pytest.mark.parametrize('document',[
    'services:\n  app:\n    build: !!str ../private\n',
    'services:\n  app:\n    build: !<tag:example.org,2026:reviewed> ../private\n',
    '%TAG !policy! tag:example.org,2026:\n---\nservices:\n  app:\n    !policy!reviewed build: ../private\n',
])
def test_equivalent_yaml_tag_spellings_cannot_bypass_policy(document):
    from scripts.distribution_policy import validate_compose_policy
    with pytest.raises(ValueError,match='Unsupported Compose override syntax'):
        validate_compose_policy(document)


@pytest.mark.parametrize('path',['compose.yaml','deployment/compose.public.yaml'])
def test_project_compose_documents_remain_valid(path):
    from scripts.distribution_policy import validate_compose_policy
    validate_compose_policy((ROOT/path).read_text())


def test_missing_parser_returns_sanitized_nonzero_preflight(monkeypatch,capsys):
    import sys
    guard=load('ci_guard')
    monkeypatch.setattr(guard,'check_identity',lambda expected:None)
    monkeypatch.setattr(guard,'private_history',lambda:False)
    monkeypatch.setattr(sys,'argv',['ci_guard.py','preflight'])
    monkeypatch.setitem(sys.modules,'yaml',None)
    assert guard.main()==1
    captured=capsys.readouterr()
    assert captured.out=='CI guard FAIL: Compose policy requires the declared PyYAML dependency\n'
    assert captured.err==''
