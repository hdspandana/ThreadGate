"""One path policy for source ZIPs and the single approved Docker build context.

This is a named-path boundary, not a universal content/secret detector. Keep the
mandatory secret audit and owner review. Docker execution/image inspection is a
separate runtime check. Unknown top-level paths are excluded by default.
"""
from __future__ import annotations
from fnmatch import fnmatchcase
from pathlib import Path, PurePosixPath, PurePath

FOLDERS = ('app','src','tests','docs','eval','scripts','.github','deployment')
DATA_FOLDERS = ('data/cases','data/records','data/assurance')
TOP = ('README.md','PRIOR_WORK.md','Makefile','pytest.ini','requirements.txt',
       'requirements.lock','requirements-browser.txt','requirements-assurance.txt',
       '.gitignore','.gitattributes','.env.example','Dockerfile','.dockerignore',
       'compose.yaml','LICENSE','LICENSE.md','LICENSE.txt',
       '.streamlit/config.toml','results/latest.json')
# Directory/file names that must never hitchhike anywhere inside an allowed tree.
BLOCKED_NAMES = ('.git','.venv','venv','env','node_modules','__pycache__',
    '.pytest_cache','.cache','.mypy_cache','.ruff_cache','.tox','.nox','.next',
    '.npm','.docker','.ssh','.aws','.azure','.config','.local','.playwright-cli','.DS_Store','.coverage','.venv*','release','runs','logs','snapshots','backups',
    'workspace-snapshots','build','dist','coverage','reviewer-responses','private-labels',
    'COORDINATOR-ONLY*','ThreadGate-*','*.egg-info','*.dockerignore',
    'secrets.toml','secrets.json','secrets.yaml','secrets.yml','secrets.txt',
    'credentials','credentials.*','service-account*.json','token.json','tokens.json',
    'token','tokens','token.txt','tokens.txt','.npmrc','.pypirc','pip.conf','*.token','.netrc','.git-credentials','id_rsa','id_ed25519',
    '*.sqlite3-*','*.sqlite-*','*.db-*','eval_*.json','*~')
# Case-insensitive extensions, using Docker/Go-compatible character classes.
EXTENSIONS = ('zip','tar','gz','tgz','bz2','xz','7z','rar','whl','backup','bak','old',
              'orig','save','tmp','temp','pyo','db','sqlite','sqlite3','pem','key','p12','pfx','pyc','log')


def extension_pattern(extension):
    return '*.'+''.join('['+c.lower()+c.upper()+']' if c.isalpha() else c for c in extension)


DENY = BLOCKED_NAMES + tuple(extension_pattern(e) for e in EXTENSIONS) + (extension_pattern('zip')+'.*',)


def prohibited(rel):
    """Path-only check shared with the verifier. Never read protected contents."""
    rel=PurePosixPath(rel.as_posix() if isinstance(rel,PurePath) else str(rel))
    if not rel.parts or rel.is_absolute() or '..' in rel.parts or '\\' in str(rel):return True
    if str(rel) in {'.env.example','.dockerignore'}:return False  # The sole approved env template.
    return any(part=='.env' or part.startswith('.env.') or
               any(fnmatchcase(part,pattern) for pattern in DENY) for part in rel.parts)


def allowed(rel):
    rel=PurePosixPath(rel.as_posix() if isinstance(rel,PurePath) else str(rel))
    if prohibited(rel):return False
    name=rel.as_posix()
    return (name in TOP or rel.parts[0] in FOLDERS or
            any(name.startswith(prefix+'/') for prefix in DATA_FOLDERS))


def docker_rules():
    # Explicit parents keep Docker traversal working under the default-deny rule.
    rules=['**']
    for name in TOP:
        parent=PurePosixPath(name).parent.as_posix()
        if parent!='.':rules.append('!'+parent+'/')
        rules.append('!'+name)
    for folder in FOLDERS:
        rules.extend(['!'+folder+'/','!'+folder+'/**'])
    rules.append('!data/')
    for folder in DATA_FOLDERS:rules.extend(['!'+folder+'/','!'+folder+'/**'])
    # Recursive env-secret denial, then the root-only approved template exception.
    rules.extend(['**/.env','**/.env.*','!.env.example'])
    rules.extend('**/'+pattern for pattern in DENY)
    rules.append('!.dockerignore')  # Root policy is required in the source distribution.
    return rules


def dockerignore_text():
    return ('# Approved default-deny distribution policy; see scripts/distribution_policy.py.\n'
            '# Changes require policy review and regression tests. No later re-inclusions.\n'
            +'\n'.join(docker_rules())+'\n')


def validate_docker_policy(text):
    rules=[line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if rules!=docker_rules():
        raise ValueError('Docker ignore rules differ from approved distribution policy')


def check_docker_context(root, context='.', dockerfile='Dockerfile', additional_contexts=None):
    """Only the reviewed repository-root context/default Dockerfile is supported.

    Alternate contexts, named contexts and alternate ignore files require a new
    explicit review, not a fallback to a weaker set of rules.
    """
    root=Path(root).resolve()
    if ((root/str(context)).resolve()!=root or str(dockerfile)!='Dockerfile'
        or additional_contexts):
        raise ValueError('Unapproved Docker context or Dockerfile override')
    if not (root/'Dockerfile').is_file():return  # Source-only fixture/repository.
    if (root/'Dockerfile').is_symlink() or (root/'.dockerignore').is_symlink():
        raise ValueError('Symlinked Docker policy/recipe is not approved')
    # Dockerfile-specific ignore files override .dockerignore: reject them all.
    if any(p!=root/'.dockerignore' and (p.parent==root or allowed(p.relative_to(root).parent/'placeholder.py'))
           for p in root.rglob('*.dockerignore')):
        raise ValueError('Unreviewed Docker-specific ignore override')
    validate_docker_policy((root/'.dockerignore').read_text())
    if any(p.is_symlink() and allowed(p.relative_to(root)) for p in root.rglob('*')):
        raise ValueError('Symlink in approved Docker context')
    for name in ('compose.override.yaml','compose.override.yml','docker-compose.yaml',
                 'docker-compose.yml','docker-compose.override.yaml','docker-compose.override.yml'):
        if (root/name).exists():raise ValueError('Unreviewed Compose override file')
    for compose in (root/'compose.yaml',root/'deployment/compose.public.yaml'):
        if compose.is_file():validate_compose_policy(compose.read_text())


def validate_compose_policy(text):
    """Parse without constructing objects; reject unsupported YAML structure/tags.

    Token checks distinguish actual tags/anchors from quoted text and comments.
    Node checks inspect decoded keys, not an approximation of YAML spelling.
    """
    try:
        import yaml
    except ImportError:
        raise ValueError('Compose policy requires the declared PyYAML dependency') from None
    try:
        for token in yaml.scan(text):
            if isinstance(token,(yaml.tokens.TagToken,yaml.tokens.AnchorToken,
                                 yaml.tokens.AliasToken,yaml.tokens.FlowMappingStartToken)):
                raise ValueError('Unsupported Compose override syntax')
            if isinstance(token,yaml.tokens.KeyToken) and text[token.start_mark.index:token.start_mark.index+1]=='?':
                raise ValueError('Unsupported Compose override syntax')
        document=yaml.compose(text,Loader=yaml.SafeLoader)
    except yaml.YAMLError:
        raise ValueError('Invalid Compose syntax') from None

    def inspect(node):
        if isinstance(node,yaml.MappingNode):
            for key,value in node.value:
                if not isinstance(key,yaml.ScalarNode) or key.value=='<<':
                    raise ValueError('Unsupported Compose override syntax')
                if key.value in {'build','context','dockerfile','dockerfile_inline',
                                 'additional_contexts','include','extends'}:
                    if not (key.value=='build' and isinstance(value,yaml.ScalarNode)
                            and value.value=='.' and value.style is None):
                        raise ValueError('Unapproved Compose build/context override')
                inspect(value)
        elif isinstance(node,yaml.SequenceNode):
            for item in node.value:inspect(item)
    inspect(document)
