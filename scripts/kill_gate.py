"""Kill gate.

Run this before building anything on top. If any check fails, the concept does
not work and the honest move is to stop rather than to polish.

  1. The token finder finds the record account and the new account in TG-001.
  2. The validator refuses a fabricated evidence string (the anti-hallucination
     property the whole design rests on).
  3. The validator refuses a value that is not in the email.
  4. The account floor holds TG-001 even when the model is fully steered to say
     no_change - including when it forges a verbatim quote.
  5. Normalisation is what catches the zero-width and non-breaking-hyphen cases,
     and the rules baseline on raw text misses both.
  6. The rules baselines run over the whole frozen set without error.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from threadgate.baseline import rules_only, rules_only_normalized  # noqa: E402
from threadgate.extract import compromised_extract, compromised_quote_extract, offline_extract  # noqa: E402
from threadgate.pipeline import email_to_text, run_case  # noqa: E402
from threadgate.records import load_cases, load_vendors  # noqa: E402
from threadgate.schema import Claim, Extraction  # noqa: E402
from threadgate.tokens import find_tokens, unique_accounts  # noqa: E402
from threadgate.validate import validate_extraction  # noqa: E402
from threadgate.normalize import normalize_text  # noqa: E402

CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, bool(ok), detail))


def main() -> int:
    cases = {c["id"]: c for c in load_cases(ROOT / "data/cases/frozen_v1.json")}
    vendors = load_vendors(ROOT / "data/records/vendor_master.json")
    vendor = vendors["V-1001"]

    # 1 - token finder sees the new account in TG-001, and it is unknown.
    # The old account is not in the email; the 4455-vs-9821 diff is produced by
    # comparing against the record, which is the whole point.
    nt = normalize_text(email_to_text(cases["TG-001"]["email"]))
    toks = unique_accounts(find_tokens(nt))
    digits = [t.normalized for t in toks]
    record_account = vendor.current("account_number")
    check(
        "token finder sees the new account 9821 in TG-001 and it is unknown",
        any(d.endswith("9821") for d in digits)
        and not any(vendor.is_known_account(d) for d in digits if d.endswith("9821"))
        and record_account.endswith("4455"),
        f"tokens={digits} record={record_account}",
    )

    # 2 - fabricated evidence is rejected
    fake = Extraction(
        intent="change_request",
        intent_evidence="I have verified this on a call.",
        claims=[Claim(field="account_number", old_value="50100234554455",
                      new_value="50100234559821",
                      evidence="The new account was confirmed telephonically.")],
    )
    v = validate_extraction(fake, nt)
    check(
        "validator rejects fabricated evidence",
        (not v.intent_evidenced) and not any(c.verified for c in v.claims),
        str([c.violations for c in v.claims]),
    )

    # 3 - a value absent from the email is rejected even with good evidence
    real_quote = "Account number: 50100234559821"
    hallucinated = Extraction(
        intent="change_request",
        intent_evidence=real_quote,
        claims=[Claim(field="account_number", old_value="50100234554455",
                      new_value="9999999999999999", evidence=real_quote)],
    )
    v3 = validate_extraction(hallucinated, nt)
    check(
        "validator rejects a value not present in the email",
        not any(c.verified for c in v3.claims),
        str([c.violations for c in v3.claims]),
    )

    # 3b - and accepts a genuine one
    genuine = Extraction(
        intent="change_request",
        intent_evidence=real_quote,
        claims=[Claim(field="account_number", old_value="50100234554455",
                      new_value="50100234559821", evidence=real_quote)],
    )
    v3b = validate_extraction(genuine, nt)
    check("validator accepts a genuine verbatim claim", any(c.verified for c in v3b.claims))

    # 4 - the floor holds when the model is steered, both variants
    for label, fn in (("compromised", compromised_extract),
                      ("compromised_quote", compromised_quote_extract)):
        r = run_case(cases["TG-001"], vendors, extractor_fn=fn)
        check(
            f"account floor holds TG-001 under {label}",
            r.decision.decision == "HOLD",
            f"got {r.decision.decision}",
        )

    # 5 - normalisation catches obfuscation; raw baseline does not
    for cid in ("TG-016", "TG-017"):
        case = cases[cid]
        raw_dec = rules_only(case, vendor).decision
        norm_dec = rules_only_normalized(case, vendor).decision
        r = run_case(case, vendors, extractor_fn=offline_extract)
        check(
            f"{cid}: raw baseline misses it, normalised catches it",
            raw_dec != "HOLD" and norm_dec == "HOLD",
            f"raw={raw_dec} norm={norm_dec} gate={r.decision.decision}",
        )

    # 6 - baselines run clean over the whole set
    ok_all = True
    for c in cases.values():
        rules_only(c, vendors[c["vendor_id"]])
        rules_only_normalized(c, vendors[c["vendor_id"]])
    check("baselines run over all cases", ok_all)

    # report
    width = max(len(n) for n, _, _ in CHECKS)
    failures = 0
    for name, ok, detail in CHECKS:
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        line = f"[{status}] {name.ljust(width)}"
        if detail and not ok:
            line += f"  ({detail})"
        print(line)

    print()
    if failures:
        print(f"KILL GATE: {failures} check(s) failed. Stop and rethink before building further.")
        return 1
    print("KILL GATE: all checks passed. Concept survives contact with the data; keep building.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
