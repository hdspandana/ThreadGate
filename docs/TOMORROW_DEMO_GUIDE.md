# ThreadGate — tomorrow’s live demonstration

## Read this first: verified demo status

**The actual Streamlit workbench is running on port 8501 and was exercised in a
real Chromium browser.** Open the Arena live preview labelled **ThreadGate —
verified live demo**. This is the real `app/workbench.py`, not the removed static
HTML preview. It is synthetic-only, unauthenticated and uses the Offline engine.
No Gemini call or payment execution is part of this demonstration.

After explicit owner permission to account for runtime storage separately, the
existing requirements.lock and requirements-browser.txt were installed without
changing their pins. The running server now uses a new isolated Python 3.13
virtual environment whose `pip check` reports **No broken requirements found**.
Browser binaries and required OS libraries were also installed outside the
source workspace. This environment is ephemeral and may not survive a sandbox
reset; your own local virtual environment remains the reliable fallback.

Verified through the actual UI: CLEAR, REVIEW, HOLD, the three paste inputs,
empty/malformed input, missing-key failure without stale success, Evaluation,
About, compromised-output Attack Lab, synthetic verification/replay and JSON
export. A completed desktop/mobile flow had zero JavaScript and HTTP errors,
and no page overflow at 390px. The three main scenarios were rerun successfully
after switching the live server into the isolated environment.

The authenticated analyst → verifier → auditor browser regression also passed
in that isolated environment. It uses separate synthetic accounts and its
existing fixed-date test wrapper; it is not a live human callback or an owner
account, and is separate from the real-clock port-8501 workbench.

**Before presenting:** open your own demo-machine browser, repeat the three
cases, and check the projector resolution. These executed checks do not replace
a full release gate, actual Docker/image inspection, live Gemini evaluation or
independent human/security review. Do not claim production or payment safety.

The earlier `ThreadGate-Local-VSCode-Source.zip` predates this UI/demo work and is
not silently replaced. Use the current checkout, or apply the separately supplied
`ThreadGate-Demo-Updates.patch` to an untouched extraction of that exact ZIP:

```sh
# In the extracted ThreadGate folder, using a local Git installation:
git apply --check ../ThreadGate-Demo-Updates.patch
git apply ../ThreadGate-Demo-Updates.patch
```

No GitHub connection, author configuration or commit is required for `git apply`.
Do not apply the patch twice or to an already modified checkout. Review it first.
The private engineering history must remain private; a source export does not
resolve publication/history review.

## A. Startup: one Streamlit server, not separate frontend/backend services

`app/product.py` is the authenticated team application. `app/workbench.py` is
the existing unauthenticated, **synthetic-only** demonstration workbench.
`scripts/serve.py` launches the appropriate entry point. The Python backend
pipeline runs within the Streamlit server; there is no npm frontend build or
separate REST backend to start. Do not expose the synthetic workbench publicly
or use real bank details in it.

### macOS / Linux, in the project root

```sh
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install --no-cache-dir -r requirements.lock
export THREADGATE_SKIP_DOTENV=1
python -B scripts/demo_check.py
python scripts/serve.py --demo --no-install --address 127.0.0.1 --port 8501
```

### Windows PowerShell, in the project root

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --no-cache-dir -r requirements.lock
$env:THREADGATE_SKIP_DOTENV = "1"
python -B scripts/demo_check.py
python scripts/serve.py --demo --no-install --address 127.0.0.1 --port 8501
```

If PowerShell blocks activation, use `.venv\Scripts\python.exe` directly for
all subsequent Python commands; do not disable machine-wide execution policy.
The lock targets Python 3.13/Linux and was successfully installed into a new
isolated Python 3.13 environment here, together with the declared browser test
extra. Windows/macOS wheel availability remains untested. Treat any local pip
resolution error as a blocker, not a reason to remove security dependencies.

Open **http://127.0.0.1:8501** on that same machine. Health check:

```sh
curl --fail http://127.0.0.1:8501/_stcore/health
```

Look for the investigation desk, Offline engine, sidebar masking control and
scenario selector. Health alone does not prove the page executed without errors.
Inspect the browser console and exercise the page after every restart.

### Optional: authenticated team demonstration

In the same activated environment, initialise a private, local demo workspace:

```sh
python scripts/manage_workspace.py --username owner
python scripts/serve.py --no-install --address 127.0.0.1 --port 8501
```

The first command prompts for a unique password of at least 14 characters; there
are **no default credentials**. Do not put passwords in commands or slides.
An administrator creates separate analyst, verifier and auditor users in Team
administration. Use separate browser profiles/private sessions for each role.
The administrator is not the analyst: sign in as the analyst to use New
investigation. Respect any existing enforced MFA policy; do not disable it for
convenience. Prepare accounts before presenting; never expose MFA enrollment
secrets, provisioning URIs, session tokens or real data on a projector.

Default SQLite locations are under ignored `data/runs/`. `THREADGATE_WORKSPACE_DB`
(team) and `THREADGATE_DB` (synthetic attestation store) can select private,
persistent local paths. Do not point this demonstration at a production database.

### Keys and environment

**No API key is needed** for the rehearsed offline flow or demo checks. Offline
is a deterministic test double, not measured AI performance. The applications
now default to offline, including when an environment key exists. Explicitly
select Gemini only with an approved budget and permission-safe inputs.

For separately authorised live use, both `GEMINI_API_KEY` and `GOOGLE_API_KEY`
are supported; the former takes precedence after placeholder cleanup. Use one
valid key from a secure environment/secret store, not a slide or source file.
`THREADGATE_MODEL` selects the configured model; see `.env.example`. Do not
check in `.env`. Missing/placeholder keys must fail, never silently fall back
from live Gemini to offline. Both Compose configurations forward both supported
key names using empty-default optional interpolation. They were statically
checked, **not run with Docker**.

### Common startup problems

| Symptom | Action |
|---|---|
| `streamlit is not installed` | Confirm the activated interpreter; install the documented lock on your local machine. `--no-install` deliberately prevents surprise installation. |
| Missing `dotenv` / `pyotp` | Use the full documented dependency set; do not stub modules for the live demo. |
| Port 8501 occupied | Stop only your known previous app, or use `--port 8502` and update the browser URL. |
| Remote preview cannot connect | A remote sandbox needs `--address 0.0.0.0` and its supplied preview URL; localhost in your browser refers to your own computer. Keep the anonymous workbench restricted. |
| No New investigation page | Use an analyst account; admin accounts manage users and audit. |
| Existing owner bootstrap refused | Reuse the intended workspace; do not delete the database to bypass controls. |
| An old CLEAR becomes REVIEW | Check reference freshness and the machine clock. Do not move the clock, edit frozen labels or relax freshness to force a desired outcome. |
| Input pasted from a fixture changes outcome | Scenario headers/context matter. Use the specifically verified paste examples below. A copied body alone is not necessarily the same input. |
| Missing key / API quota / timeout | Keep the result fail-closed. Return to the explicitly labelled offline demonstration, never pretend it is live Gemini. |
| Old success disappears after a failed retry | Intentional reliability fix: previous results are invalidated before retrying. |

## B. Rehearsed 5–7 minute flow (target 6:30)

**0:00–0:40 — Problem.** “A convincing vendor email can redirect a payment.
ThreadGate asks whether the requested action agrees with a trusted record. It is
not a general spam detector, fraud probability score or payment processor.”

**0:40–1:15 — Architecture.** Point to the engine selector. “AI may propose an
interpretation with quotations. Normalisation, independent destination scanning,
evidence validation, trusted-record comparison and deterministic rules control
the final gate. An untrusted model cannot authorise or downgrade the decision.
Today I am using the labelled offline test double, not claiming Gemini accuracy.”

**1:15–2:00 — CLEAR.** Investigate → Scenario inbox → click **Select a
synthetic request**, type **TG-007**, select its matching option → **◈ Inspect
request**. The dropdown is searchable; typing the ID avoids scrolling past it.
Point to CURRENT reference, CLEAR banner and the explicit “not approval” warning.
Show the Control trace tab. “No change was identified in this supported example;
this does not authenticate the sender or guarantee the email is safe.”

**2:00–2:50 — REVIEW.** Search/select **TG-012** in the same dropdown → **◈ Inspect request**. A result is not reused after
input changes. Show the trusted-to-requested comparison and the alternate
routing finding. “Even a registered alternate destination needs human review
and attestation. Familiar does not mean automatically authorised.”

**2:50–3:45 — HOLD.** Search/select **TG-001** → **◈ Inspect request**. Open Evidence & destination
diff and Control trace. Leave values masked unless deliberately explaining
these synthetic fixtures. “The unknown account token independently raises the
floor. Contact the vendor through the trusted record, never the replacement
contact in the email. HOLD is not an accusation of fraud.”

**3:45–4:30 — Adversarial boundary.** Switch to Attack Lab, choose the
`compromised` simulated extractor, select TG-001 and inspect. It still HOLDs.
“This is a deterministic simulation of suppressed model output, not a live
prompt-injection benchmark and not a proof against every attack.” For a short
demo, omit the full attack matrix to avoid extra output/navigation.

**4:30–5:20 — Human workflow.** On the synthetic Verification & report tab,
show trusted contact guidance and the explicit DEMO VERIFICATION warning. The synthetic storage flow was browser-tested here: click both confirmation
labels and **Record synthetic verification**; Workflow becomes DEMO_RECORDED.
Click **Test replay of the same event** to see ATTESTATION_REPLAY. The gate stays HOLD.
Do not claim the synthetic event authenticates a person or proves a callback.
For an actual authenticated workflow, use the pre-provisioned analyst/verifier
sessions instead: investigate → save → independently assign → re-inspect →
attest → audit. That flow passed in a separate synthetic browser regression here, but your
own accounts and deployment still need local rehearsal.

**5:20–6:00 — Traceability.** Show finding codes, evidence and minimal report
export. Downloads may contain sensitive context depending on the screen; use
synthetic data only and inspect exports before sharing. The team audit stores
transactional history but is not externally anchored or tamper-proof.

**6:00–6:30 — Conclusion.** “ThreadGate keeps interpretation separate from
control. It deliberately adds friction when evidence or references are not
trustworthy. It does not execute payments, prove callback completion, replace
independent security review, or establish provider accuracy from offline runs.”

## C. Demo cases: observed outcomes, not invented screenshots

These cases were executed against the actual Python pipeline and the three
primary outcomes plus paste variants were entered through the real browser UI.
The script uses the real system clock; references were CURRENT in these runs.
Re-run immediately before presenting: freshness is a real security input.
No frozen labels, denominators, reference dates or scoring rules were changed.

### Verified paste inputs

In Investigate → Paste email, select **V-1001 / Northwind Logistics**, keep
Offline selected, paste one body below and click Inspect. These exact bodies
were additionally run with the UI's blank sender / `Pasted request` subject.

### CLEAR — explicit no-change

```text
No change to our payment details.
```

**Observed: CLEAR. Why:** An explicit evidenced no-change statement with a current reference.
**On screen:** Blue CLEAR label; no safety/payment guarantee.

### REVIEW — registered alternate

```text
Hi,

For the October cycle please use our alternate collections account 50100234558812, IFSC HDFC0001234, beneficiary Northwind Logistics Pvt Ltd. It is the one we registered with you in July for collections.

Thanks,
Meera
```

**Observed: REVIEW. Why:** A pre-registered alternate still invokes the independent routing/review floor.
**On screen:** Alternate destination finding and human-verification requirement.

### HOLD — new destination

```text
Hi Team,

Following the finance system migration we completed last week, please update the account used for our payments with immediate effect.

Beneficiary: Northwind Logistics Pvt Ltd
Bank: HDFC Bank Ltd
Account number: 50100234559821
IFSC: HDFC0001234

Everything else stays exactly the same. Please confirm once this is updated in your system.

Regards,
Meera Iyer
Finance Controller, Northwind Logistics
```

**Observed: HOLD. Why:** The requested account is not an accepted destination in the trusted record.
**On screen:** Unknown-token finding, changed destination, trusted-contact checklist.

### Additional executed checks

| Check | Observed | Meaning |
|---|---|---|
| TG-007 / TG-012 / TG-001 complete scenario inputs | CLEAR / REVIEW / HOLD | Actual scenario-inbox fixtures, with full original headers/context. |
| TG-020 incomplete change request | HOLD | An unspecified destination is not invented. |
| `Please update account number: 98989898989898.` | HOLD | Unknown synthetic destination. |
| `Please update account number: ABCD1234567890.` | HOLD | Mixed malformed account value is not silently repaired. |
| Unknown vendor ID with no-change text | HOLD / MISSING | No trusted reference means no usable payment verification. |
| TG-001 with compromised-output simulation | HOLD | Independent destination controls survive suppressed interpretation. |
| Synthetic adapter exception | HOLD | Provider failure is not a successful AI result. |
| Invented no-change evidence on TG-001 | HOLD | Unsupported evidence cannot remove the independent finding. |
| Non-text email body | REJECTED | Programmatic invalid-input validation, not a UI status. |
| Over-limit body | REJECTED | Programmatic size bound; UI paste input is separately limited to 20,000 characters. |

The body-only paste of the longer TG-007 email returned HOLD in pipeline rehearsal because its intent
was not justified without the original header/context. This limitation was not
hidden or “fixed” by relaxing evidence checks. Use the verified short no-change
paste or the complete Scenario inbox fixture for CLEAR.

An empty paste does not produce a decision: the actual browser showed the
input guidance and no Inspect button. The malformed-account paste also HOLDed
in the actual interface.
Use `python -B scripts/demo_check.py` for all **15** no-provider checks. It returns
nonzero if any expected result differs. Do not confuse these 15 scenarios with
the pytest test count or a full security assessment.

## D. Explain it simply: viva answers

**What does ThreadGate do?** It checks requested vendor payment actions against
trusted records and returns CLEAR, REVIEW or HOLD with evidence and next steps.
It neither transfers money nor authorises payment.

**Why does it matter?** Business-email-compromise messages can be fluent and
plausible. The important question is whether the requested destination/action
is authorised, not whether the prose “looks AI-generated.”

**How does it work?** Thin Streamlit UI → normalised source/tokens → structured
interpretation → evidence validation → deterministic record comparison/policy
→ human workflow and minimal reporting. The core is separate from rendering.

**What does Gemini do?** Proposes structured intent/claims and source quotations.
Its production adapter receives the request, not the trusted vendor master.
The deterministic pipeline validates its output. Gemini is optional for the
rehearsed demo and was not called during this preparation.

**Why not let the model decide?** The message is adversarial input; model output
can be wrong, manipulated, unsupported or unavailable. A supported independent
finding sets a floor the model cannot lower. Provider failures become HOLD.

**What is the trusted record?** Operator-maintained vendor destination/contact
information with version and freshness. It is not automatically updated from
an email. Missing, invalid or future-dated reference dates cannot become CURRENT.

**What is CLEAR?** No change identified by this prototype under its supported
controls. Not safe, genuine, approved or fraud-free.

**What is REVIEW?** Human review/attestation is still required; it is not release.

**What is HOLD?** Stop and verify through independently trusted contact details.
It is a conservative gate, not a fraud accusation.

**Can an employee simply override HOLD?** Verification records an attestation;
it never downgrades the underlying gate. Authenticated roles, exact request/
destination/reference binding and replay protection enforce the team workflow.
A verifier cannot provide proof that a real-world phone call actually occurred.

**What security protections exist?** Bounded inputs, escaped output, masked
recognised identifiers, schema/evidence validation, independent destination and
routing floors, stale/missing/future reference handling, separated roles,
transactional replay protection, revision checks, optional/enforced MFA,
minimal case persistence, credential/path audits and fail-closed CI evidence.
Each has finite coverage; none establishes complete security.

**Can prompt injection bypass it?** The executed finite simulations did not
release their tested HOLDs. That is not a universal prompt-injection proof or
a measured live Gemini robustness score.

**Is an offline perfect score AI accuracy?** No. Offline is a deterministic test
double used for reproducibility. Live development/held-out evaluation and actual
independent adjudication are separate tasks. We did not tune held-out labels.

**Is the audit tamper-proof?** No. SQLite transactions protect local consistency,
not a privileged file administrator. External anchoring and deployment controls
would be future independently reviewed work.

**Does masking remove all personal data?** No. It recognises supported patterns;
pasted text is still visible while editing and some exports contain source.
Only synthetic or explicitly permission-safe data belongs in this demo.

**Why do the synthetic and team apps differ?** The workbench illustrates core
controls without accounts. The product adds authenticated roles and shared
state. Do not present synthetic verification as authenticated team operation.

**What remains limited?** Finite token/evidence/language coverage; trusted-record
quality; unsupported routing formats; provider availability; no SSO/distributed
abuse controls; single-host persistence; no bank/ERP execution; no externally
anchored audit; outstanding independent usability/security review.

**What would you build next?** Validated provider evaluation, independently
reviewed UX, deployment hardening, external audit anchoring, monitored auth/SSO,
and controlled integrations. Not a rushed payment-release endpoint.

## E. Current executed checks and cleanup

### Executed in this continuation

- Pinned dependency resolution and installation succeeded. A **new isolated**
  Python 3.13 environment installed requirements.lock and the existing browser
  test requirement. `pip check`: **No broken requirements found**.
- **132 passed, zero skips** in targeted workbench/AppTest, app hardening,
  product integration, reference-date, UX/guard and mocked model-failure tests.
- The current synthetic pipeline checker passed **15/15** in the isolated runtime.
- Real Chromium, actual port-8501 app, real system clock: TG-007 CLEAR, TG-012
  REVIEW, TG-001 HOLD; all three rerun after isolated-runtime restart.
- Real UI paste cases: explicit no-change CLEAR, registered alternate REVIEW,
  new destination HOLD, malformed account HOLD, empty-input guidance, missing-key
  error with no stale result. No provider call was made.
- Real UI Evidence/Control trace/Verification tabs, synthetic event receipt,
  replay rejection and privacy-minimised report download passed. HOLD stayed HOLD.
- Evaluation, About and compromised-output Attack Lab navigation passed.
- A completed main flow recorded **0 JavaScript page errors, 0 HTTP errors** and
  no page overflow at **390px**. This is not full accessibility conformance.
- The existing authenticated browser script passed in the isolated runtime:
  analyst → independent verifier → auditor, persisted VERIFIED workflow, HOLD
  gate preserved, JSON bundle, masking/reveal, keyboard login/focus and mobile.
  It explicitly pins its **test reference date to 2026-10-06** and uses temporary
  accounts, not your real accounts. Its temporary database is not the live demo DB.
- One stale assertion in scripts/browser_smoke.py was aligned with the already
  shipped error mentioning **both** supported key names. No application or
  security-rule change was required in this continuation.

The first browser setup failed on /opt permissions and then a missing libnspr4;
using the supported package-local browser location and installing required OS
libraries resolved those issues. Early automation needed searchable-dropdown,
checkbox-label and page-rerender synchronization corrections. The completed
reruns above passed; no security check was disabled to make them pass.

The first shared-runtime installation exposed an unrelated numba/NumPy conflict.
Do not use that shared interpreter as the demo environment. The running server
uses the isolated environment, which passes dependency checks. Runtime packages,
browsers and OS libraries are accounted separately under the explicit permission;
the source workspace still keeps its 128,000,000-byte ceiling and reserve.

### Still not verified

No full release gate, actual Docker context/image inspection, public deployment,
remote CI, paid live Gemini evaluation or independent human review is claimed.
The new isolated dependency install is not a fresh-source-extraction release test.
Windows/macOS and your own projector/browser need rehearsal. pyflakes was not
installed merely for the demo. Earlier 543-pass/8-skip and 199-pass results are
historical; the current targeted result is the 132-pass run above.

### Cleanup and preservation

Previous cleanup reclaimed **2,096,640 allocated bytes** from inspected synthetic
pytest temporary folders. In this continuation, the obsolete static
`/home/user/ThreadGate-UI-Preview.html` was removed (**8,192 allocated bytes**).
The source ZIP and update patch were retained because they are the local handoff,
not discarded as duplicates. The patch is refreshed rather than creating another
ZIP. One actual live-browser screenshot is retained as current evidence.

No tracked source/test/docs/assets, old checkouts, original evidence, original
databases, Git history or old ZIP deliverables were deleted. Do not run the
generic clean script indiscriminately: data/runs can contain real local databases.
The source, labels, scoring and deterministic policy were not changed here.

### Exact sandbox restart (if the current process stops)

Run from /home/user/ThreadGate-assurance; these ephemeral paths are specific to
this sandbox, not requirements for your local machine:

```sh
PYTHONDONTWRITEBYTECODE=1 THREADGATE_SKIP_DOTENV=1 \
THREADGATE_DB=/usr/local/lib/python3.13/site-packages/.threadgate-demo-runtime/attestations.sqlite3 \
/usr/local/lib/python3.13/site-packages/.threadgate-demo-runtime/app-env/bin/python -B \
scripts/serve.py --demo --no-install --address 0.0.0.0 --port 8501
```

Keep it in a persistent terminal/process. If the sandbox resets, reinstall the
runtime or use your own machine; installed runtime files are not source deliverables.
Do not print or reuse the separate browser regression's random test password.

## F. Final rehearsal checklist

- [ ] Install and launch on your actual demo machine; allow no automatic paid calls.
- [ ] Run demo_check; confirm current reference state. Do not alter records to pass.
- [ ] Exercise all three verified paste inputs and complete scenario fixtures.
- [ ] Inspect Evidence, Control trace, error/empty states and Evaluation navigation.
- [ ] Check phone-width layout, keyboard navigation, masked values and console errors.
- [ ] Rehearse synthetic verification/replay only if storage works locally.
- [ ] If showing team workflow, pre-provision independent accounts and test MFA policy.
- [ ] Use synthetic data, hide terminal secrets and close unrelated browser tabs.
- [ ] State limitations and distinguish offline, simulated, live and human evidence.
- [ ] Do not push this private-history branch or claim production/release readiness.

## Final cleanup and storage ledger

Exact removed paths (all inspected synthetic pytest output, except obsolete HTML):

- data/runs/audit-fixes-tests
- data/runs/closure-tests
- data/runs/integration-fixes-tests
- data/runs/final-integration-policy-tests
- data/runs/final-integration-ci-tests
- data/runs/demo-ui-checks
- data/runs/demo-ux-tests
- data/runs/demo-regressions
- /home/user/ThreadGate-UI-Preview.html

Combined allocated bytes reclaimed: **2,104,832**. No blanket clean was run.
New test/browser output in this continuation is outside the source workspace.
The original ZIP is unchanged; the existing patch is refreshed to ten files,
including the corrected browser regression assertion and this guide. Its reverse
application check passes against the current checkout; forward application into
a fresh extraction was not performed here. No new archive was made.

The synthetic Attack Lab browser matrix also passed: **48 runs**, zero provider
calls and zero human participants. This is synthetic evidence, not a live-model
or human attack-resistance claim.

Final allocated workspace/source: **109,450,240 bytes**; ceiling 128,000,000;
headroom **18,549,760 bytes**, exceeding the 5,000,000 reserve.

Separate authorized ephemeral Python-package/runtime/browser tree:
**3,412,386,304 allocated bytes total**, versus **1,741,782,528** before installation;
net increase **1,670,603,776 bytes**. This includes the isolated app
environment and managed browser binaries (712,059,904 bytes). The OS library
installer additionally reported approximately **121 MB** of additional system
packages; that is its estimate, not an exact allocated-byte measurement. Runtime
storage is not included in or exported with the source workspace. Shared runtime
packages are retained rather than deleting dependencies of unrelated software.
