# Mandatory evidence and distribution boundaries

This checkpoint changes only CI evidence acceptance and distribution filtering.
It does not certify a release, provider accuracy, independent adjudication or a
clean image. The private engineering branch/history is not a public-release base.

## Evidence acceptance

The release workflow must invoke source and extracted validation through
`ci_guard.py run`. Missing optional diagnostics on other commands do not require
a pytest report. Missing mandatory source/extracted evidence fails the wrapper,
including when its child exits zero. Workflow upload remains success- and
owner-approval-gated after the required browser/container jobs, source gate,
commit/archive verification and extracted checks.

Mandatory evidence requires the exact ordered phase checks, successful exits,
nonempty passing test outcomes and no failures/errors. Source requires no skips.
The extracted phase permits only the existing named no-Git history diagnostic
skip, identified from its JUnit classname/name/reason; no new skip is authorized.
Counts represent JUnit outcome records. Warnings are optional numeric diagnostics
from a recognized pytest summary; absent warning evidence stays null, not zero.

The wrapper invalidates only its disposable per-phase report before execution.
It independently observes clean Git HEAD before and after the child, compares it
to the event SHA, and binds the report to a new invocation ID, workflow run/attempt
and phase. The writer separately observes the actual source checkout. Extracted
source still must match the verified archive/manifest commit. These unsigned local
records are not an external trust anchor against a privileged runner writer.
Only allowlisted metadata, counters and check statuses reach CI output, not test
names, inputs, failure messages or raw command output.

## Distribution acceptance

`scripts/distribution_policy.py` defines the common packager/verifier path policy
and canonical `.dockerignore`. Docker starts default-deny, allows the application,
tests, locks, reviewed documentation/configuration and required synthetic fixtures,
then recursively excludes private review material, known credential/environment
paths, Git metadata, environments/caches, runtime files, backups and archives.
The root `.env.example` is the approved environment-template exception.

Required source filenames (including `tokens.py`) are not confused with token
files. The policy is path-based, not universal content DLP: the mandatory secret
audit, provenance/licensing review and owner content review remain necessary.
Historical diagnostic `secrets.txt` is no longer distributed; it is not deleted.

The workflow builds through `ci_guard.py docker-build -t threadgate:ci .`.
Only the repository-root/default-Dockerfile context and these options are approved.
Named/alternate contexts, alternate recipes/ignore files, allowed-tree symlinks
and unreviewed Compose build overrides fail closed. The checked canonical ignore
rules cannot be removed or extended with a re-inclusion. Builds outside this
approved entrypoint are not certified by this guard.

## Validation boundaries

Focused regressions mock command execution, installation and extraction. No Docker,
archive, extracted install, full runtime gate, remote CI or live provider validation
is performed by those mocks. Actual Docker context/image inspection and full
source/extracted/browser/recovery validation must run later on the authorized,
adequately provisioned runner against the eventual committed candidate.

## Final integration corrections

Compose policy is now checked with PyYAML scanner tokens and unconstructed safe
nodes. Actual explicit tags (including custom-tagged build keys), aliases/anchors,
flow mappings and unsupported build/context fields fail closed. Similar text
inside scalar strings or comments is not treated as a YAML tag. Parser errors
and an unavailable parser fail with fixed diagnostics, not raw YAML contents.

PyYAML 6.0.3 is declared in the lock and compatibility requirements. Each CI job
sets up the pinned Python action, checks runner capacity, and installs only the
pinned parser through the diagnostic wrapper before preflight. No dependency
installation was performed in this workspace. Updated clean dependency installs,
remote bootstrap execution and real Docker inspection remain NOT RUN.

Both base and public-overlay Compose environments forward GEMINI_API_KEY and
GOOGLE_API_KEY using empty-default optional interpolation. No key value is stored
in these files; environment files remain excluded from distribution. Application
placeholder rejection and key selection are unchanged.
