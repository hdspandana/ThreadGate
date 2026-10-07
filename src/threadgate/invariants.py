"""AI-independent invariants.

These checks never see the model's output. They exist so that a model which has
been steered, poisoned or simply hallucinated cannot buy an unsafe outcome.

I1 - Unknown account floor. If a number in the email looks like a bank account
     and it is not the account we hold for this vendor, and not one of the
     pre-registered alternates, a human has to look at it. Full stop. The model
     is not asked, and its answer cannot override this.

I2 - No-change must be evidenced. An intent of "no_change" is only accepted if
     the model quotes the sentence that says so. An unevidenced no_change is
     downgraded to `unverifiable` and falls through to the deterministic
     change-act detector.

I3 - Change act with nothing verifiable. If the email asserts a change in
     payment language but the validator admitted no values, hold it. This is the
     token-less request: "new details are in the attached PDF".

I2c - A "confirmation_request" verdict must be justified the same way a
      "no_change" one is: the quote has to ask us to confirm something, and
      must not issue a change in the same breath.

I5 - Pre-registered alternate in a routing instruction. I1 holds on
     destinations we do not recognise and is silent on ones we do, which is
     right for that question but leaves the decision to the model whenever the
     account named is a real alternate the vendor already registered. I5 gives
     that case an AI-independent floor of REVIEW: known, not currently active,
     and named in a sentence that tells the reader to route money to it.

What these three do NOT cover is stated plainly in the README: a token-less
request whose change language the model also fails to report has no
AI-independent evidence at all, and only the human attestation step closes it.
"""

from __future__ import annotations

import re
from dataclasses import replace

from .actions import (
    find_actions,
    has_live_change_or_routing_action,
    live_destination_links,
)
from .records import Vendor, normalize_code
from .schema import Finding
from .tokens import Token, unique_accounts

CHANGE_WORD = re.compile(
    r"\b(chang|updat|amend|revis|replac|switch|modif|correct|transfer|"
    r"use the following|with effect|w\.e\.f|effective)\w*\b",
    re.IGNORECASE,
)

ENTITY_WORD = re.compile(
    r"\b(account|a\s*/\s*c|acct|bank|beneficiary|ifsc|iban|payment|remit|details)\w*\b",
    re.IGNORECASE,
)

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


def account_floor(tokens: list[Token], vendor: Vendor) -> list[Finding]:
    """I1a. Unknown account-like numbers present in the email."""
    findings: list[Finding] = []
    for tok in unique_accounts(tokens):
        if vendor.is_known_account(tok.normalized):
            continue
        on_file = vendor.current("account_number")
        # A record with no account on file is not a normal state and must not be
        # rendered as if one were there; it is also not a reason to skip the
        # finding, so it changes the wording and nothing else.
        on_file_hint = f"****{on_file[-4:]}" if on_file else "no account on file"
        findings.append(
            Finding(
                code="I1_UNKNOWN_ACCOUNT_TOKEN",
                severity="hold",
                message=(
                    f"Account-like number {tok.masked} appears in this email and is not "
                    f"the account on file for {vendor.display_name} "
                    f"({on_file_hint}), and is not a "
                    "pre-registered alternate."
                ),
                snippet=tok.raw.strip(),
                span_norm=(tok.start, tok.end),
                independent_of_model=True,
            )
        )
    return findings


def destination_code_floor(tokens: list[Token], vendor: Vendor) -> list[Finding]:
    """I1b. Branch/routing codes that are not associated with this vendor.

    The closed-world rule applies to every supported destination token the
    scanner can see, not only to account numbers. An IFSC, IBAN or SWIFT code in
    the email that belongs to neither the current record nor a pre-registered
    alternate is a destination we do not recognise.
    """
    findings: list[Finding] = []
    seen: set[str] = set()
    for tok in tokens:
        if tok.kind not in ("ifsc", "iban", "swift"):
            continue
        if vendor.is_known_destination_code(tok.kind, tok.raw):
            continue
        key = f"{tok.kind}:{tok.raw.strip().upper()}"
        if key in seen:
            continue
        seen.add(key)
        findings.append(
            Finding(
                code="I1_UNKNOWN_DESTINATION_CODE",
                severity="hold",
                message=(
                    f"{tok.kind.upper()} {tok.raw.strip()} appears in this email and is not "
                    f"associated with {vendor.display_name} or any pre-registered alternate."
                ),
                snippet=tok.raw.strip(),
                span_norm=(tok.start, tok.end),
                independent_of_model=True,
            )
        )
    return findings


def destination_floor(tokens: list[Token], vendor: Vendor) -> list[Finding]:
    """The whole AI-independent floor: every visible destination token."""
    return account_floor(tokens, vendor) + destination_code_floor(tokens, vendor)


# ---------------------------------------------------------------------------
# I5 - a pre-registered alternate being routed to is at least a REVIEW
# ---------------------------------------------------------------------------
# I1 asks "is this destination one we know at all?" and holds when it is not.
# It is silent when the destination IS known, which is the correct answer to
# that question - but it leaves a hole. An attacker who learns a pre-registered
# alternate account, or a genuine vendor quietly moving money to one, produces
# an email naming a destination that passes I1 and whose only remaining
# obstacle is the model's opinion of the prose. That is exactly the failure the
# architecture says must not be possible: a decision resting on AI judgement
# alone.
#
# So a destination that is known, is NOT the currently active one, and is named
# in an actionable payment-routing context gets an AI-independent floor of
# REVIEW. It is deliberately weaker than I1's HOLD - the account is a real one
# the vendor registered, so this is a change to be attested, not an unknown
# destination - and it is a floor, so nothing here can lower a decision.

# The routing vocabulary, the destination association and the polarity rule all
# live in `actions.py`, and are shared with I2b and I2c so the three invariants
# cannot disagree about what counts as an instruction.






# How far after a routing instruction a destination may be named and still be
# the thing that instruction points at. "Route payments to X" names X
# immediately; a sentence that mentions an incidentally-named account long after
# (or long before) the instruction is not routing to it. Without this bound a
# single sentence like "do not use the alternate account ..., continue to remit
# to our current account ..." reads as an instruction to pay the alternate.


def _sentences_with_offsets(text: str) -> list[tuple[str, int, int]]:
    """Sentences with their offsets, so a token can be placed in one."""
    out: list[tuple[str, int, int]] = []
    if not text:
        return out
    pos = 0
    for part in SENTENCE_SPLIT.split(text):
        idx = text.find(part, pos)
        if idx < 0:
            idx = pos
        out.append((part, idx, idx + len(part)))
        pos = idx + len(part)
    return out


def _routing_matches(sentence: str):
    """Live routing/destination actions in this sentence."""
    return [
        a for a in find_actions(sentence)
        if a.kind in ("transfer", "flow", "assign") and a.live
    ]


def actionable_routing(sentence: str) -> bool:
    """Does this sentence tell the reader to route money somewhere?

    True only for an instruction. A sentence that merely mentions an account,
    or that names one in order to say not to use it, is not an instruction.
    """
    return bool(_routing_matches(sentence))


def routing_instruction_ends(sentence: str) -> list[int]:
    """Offsets just past each actionable routing instruction in the sentence.

    Kept because the floor needs positions rather than a yes/no: knowing that a
    sentence contains an instruction is not the same as knowing which token it
    points at.
    """
    return [a.end for a in _routing_matches(sentence)]


def _alternate_destination_status(tok: Token, vendor: Vendor) -> str | None:
    """Is this token a known destination that is not the active one?

    Returns None for the current destination and for anything unknown. Unknown
    destinations are I1's job and already hold; this guard must not fire on
    them, or a REVIEW finding would sit alongside the stronger HOLD.
    """
    # `number` is admitted alongside `account`, and that is deliberate.
    #
    # The token classifier is conservative about calling a long digit run an
    # account, because invoice numbers, GSTINs and phone numbers all look like
    # one. That conservatism is right in general and wrong here: "pay future
    # invoices to 50100234558812" is classified `number` precisely because
    # "invoice" is nearby, while the number is the destination.
    #
    # Widening the candidate set is safe because the next line is the real
    # filter - the token has to be an account this vendor has actually pre-
    # registered. An invoice number is not one, so it still resolves to None.
    if tok.kind in ("account", "number"):
        status = vendor.account_status(tok.normalized)
        if status is None or status == "current":
            return None
        return status
    if tok.kind in ("ifsc", "iban", "swift"):
        if not vendor.is_known_destination_code(tok.kind, tok.raw):
            return None
        current = vendor.current(tok.kind)
        if current and normalize_code(current) == normalize_code(tok.raw):
            return None
        return "allowlisted"
    return None


def alternate_routing_floor(
    tokens: list[Token], norm_text: str, vendor: Vendor
) -> list[Finding]:
    """I5. A pre-registered alternate named in a routing instruction.

    Lives beside the destination floor and is gated by the same ablation, so
    `hybrid_no_scan` removes it too: it is part of what the closed-world scan
    buys, not a property of the model.

    The association is done by `actions.link_actions_to_destinations`, which
    binds each action to the destination token it governs and carries that
    action's polarity. Two properties follow that a windowed negation check
    could not give:

      - "Do not route to the old account; route future payments to ALT" still
        flags ALT, because the negation is spent on the first clause.
      - "Instead of the current account, route payments to ALT" still flags
        ALT, because "Instead of" attaches to the account it names, not to the
        routing verb that follows the comma.
    """
    findings: list[Finding] = []
    seen: set[tuple[str, str]] = set()

    for sentence, s0, s1 in _sentences_with_offsets(norm_text):
        in_sentence = [t for t in tokens if s0 <= t.start < s1]
        if not in_sentence:
            continue
        # Relative copies, so the action layer works in sentence coordinates
        # and no polarity leaks across a sentence boundary.
        relative = [
            replace(t, start=t.start - s0, end=t.end - s0) for t in in_sentence
        ]
        for link in live_destination_links(sentence, relative):
            index = next(
                (i for i, r in enumerate(relative) if r is link.token), None
            )
            if index is None:
                continue
            tok = in_sentence[index]
            status = _alternate_destination_status(tok, vendor)
            if status is None:
                continue
            key = (tok.kind, tok.normalized)
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                Finding(
                    code="I5_ALTERNATE_DESTINATION_ROUTING",
                    # Advisory, like the reference-state finding: this says the
                    # floor is engaged, and `policy.decide` decides the consequence.
                    severity="info",
                    message=(
                        f"{tok.kind.upper()} {tok.masked} is a pre-registered "
                        f"{'alternate' if status == 'allowlisted' else status} for "
                        f"{vendor.display_name}, but it is not the currently active "
                        "destination, and this email instructs payments to be routed "
                        "to it. A request to move money to a different destination "
                        "is at least a REVIEW no matter how the message reads."
                    ),
                    snippet=sentence.strip()[:200],
                    span_norm=(tok.start, tok.end),
                    independent_of_model=True,
                )
            )
    return findings


OUT_OF_BAND = re.compile(
    r"(attach|enclos|image|scan|pdf|screenshot|photo|snapshot|jpe?g|\.png|"
    r"spreadsheet|excel|\.xlsx?|portal|download|in the file|separate file)",
    re.IGNORECASE,
)


def out_of_band_destination(norm_text: str) -> list[Finding]:
    """I4. The email says the destination lives somewhere we cannot read.

    ThreadGate does no OCR and no attachment parsing, and it is not going to grow
    any: opening an attacker-supplied attachment to inspect it is not a control,
    it is an exposure. So when the message says the account is in an image, a PDF
    or a portal, the correct answer is the same as for any unverifiable
    destination - a human retrieves it through a channel they initiate.

    This is a sentence-level pattern over text already in the pipeline. It is not
    OCR, not URL scanning, and not attachment analysis.
    """
    for sentence in SENTENCE_SPLIT.split(norm_text or ""):
        if not sentence.strip():
            continue
        m = OUT_OF_BAND.search(sentence)
        if m and ENTITY_WORD.search(sentence):
            return [
                Finding(
                    code="I4_DESTINATION_OUT_OF_BAND",
                    severity="hold",
                    message=(
                        "The message points at a destination this pipeline cannot read "
                        f"({m.group(0).lower()}). ThreadGate does not open attachments or "
                        "images, so the destination is unverifiable and a human must "
                        "retrieve it through a channel they initiate."
                    ),
                    snippet=sentence.strip()[:200],
                    independent_of_model=True,
                )
            ]
    return []


# Matches words in the *email*, not a decision of the gate. The decision
# vocabulary is CLEAR / REVIEW / HOLD; `no_change` here is the model's
# description of what the email asks for.
#
# Every alternative below says something about whether a PAYMENT DETAIL is
# changing. That restriction is the point.
#
# The previous version also accepted `disregard`, `ignore`, `no action` and
# `was a phish`, and those are not statements about payment details - they are
# the standard vocabulary of a retraction, real or forged. Accepting them meant
# an email could carry an actionable change in one sentence and, in another,
# supply the exact words I2b was looking for. A steered model quoting only the
# second sentence got a CLEAR on a real beneficiary-name change: no destination
# token appears in that email, so nothing AI-independent caught it.
#
# They are gone, and the bare `not` / `n't` / `never` alternatives
# went with them for the same reason. A negation of a change is only a negation
# of a change when it negates a change.
NO_CHANGE_PHRASE = re.compile(
    r"("
    # a change to the payment detail is explicitly refused or denied
    r"\b(?:do|does|did|will|would|can)\s+not\s+(?:change|changing|update|updating|"
    r"amend|replace|revise)\w*"
    r"|\b(?:has|have|had)\s+not\s+(?:changed|updated|been\s+changed)\b"
    r"|\b(?:are|is|were|was)\s+not\s+(?:changing|changing|changing)\b"
    r"|\bnot\s+(?:changing|changed|updating|updated|amending|replacing|revising)\b"
    r"|\bnever\s+(?:changing|changed|updat\w*)\b"
    r"|\b(?:no|not\s+any)\s+(?:changes?|updates?|amendments?|revisions?)\b"
    r"|\bno\s+new\s+(?:bank|payment|account|remittance|beneficiary)\w*"
    r"|\bnothing\s+(?:is\s+|has\s+|will\s+|was\s+)?chang\w*"
    r"|\bwithout\s+chang\w*"
    # the detail is the same as it was
    r"|\bunchanged\b"
    r"|\bdetails?\s+(?:are|is|remain|remains|were|was|have|has)?\s*"
    r"(?:unchanged|the\s+same|correct|valid|accurate)\b"
    r"|\bremains?\s+(?:the\s+same|unchanged|as\s+(?:before|usual))\b"
    r"|\bstill\s+(?:the\s+)?(?:same|current|valid|active|correct)\b"
    r"|\bcontinue\s+to\s+use\s+(?:the\s+)?(?:current|existing|same)\b"
    r"|\bthe\s+same\b"
    r"|\bas\s+(?:before|usual)\b"
    r"|\bstands?\b"
    r")",
    re.IGNORECASE,
)


def no_change_justified(quote: str) -> bool:
    """I2b. The quote offered for a `no_change` verdict must actually say so.

    This exists because of an ablation, not a thought experiment. A steered
    model that returns no_change with *no* quote is caught by I2. A steered
    model that returns no_change with a quote copied verbatim from the email
    passes I2 - the words really are in the email - and that variant lost 3 of
    the 12 high-risk cases in the frozen set.

    So the verdict and its justification have to agree, and that is a test in
    both directions:

      1. The quote must contain a payment-domain no-change phrase. It must not
         be retraction vocabulary, which an attacker can append to any email.
      2. The quote must not carry a live change instruction of its own.

    The second half closes the mixed sentence:

        "Please update our beneficiary name; no new bank details are needed."

    The second clause is a good no-change phrase and the first is a real change.
    A model quoting the whole sentence and reporting no_change used to be
    believed. Polarity comes from the shared action layer, so "we are not
    changing our bank details" and "nothing is changing today" stay valid:
    their change verb is negated.
    """
    if not NO_CHANGE_PHRASE.search(quote or ""):
        return False
    return not has_live_change_or_routing_action(quote)


CONFIRMATION_PHRASE = re.compile(
    r"\b(?:confirm|confirmation|verif|check|clarif|let\s+us\s+know|"
    r"as\s+per\s+your\s+records|is\s+this\s+(?:right|correct))\w*",
    re.IGNORECASE,
)

# The change verbs from CHANGE_WORD minus `correct`. "Our correct bank details"
# is not a request to correct anything - it is the word being used as an
# adjective, and `change_act_detected` accepts it only because that function
# exists to escalate and a crude detector there costs review time rather than
# safety. Using it here would reject TG-011, whose whole content is a request to
# confirm that the details on file are correct.
def confirmation_request_justified(quote: str) -> bool:
    """I2c. Does the quote ask us to confirm, without asking us to change?

    Both halves matter.

    "Can you confirm you have our correct bank details on file?" is a
    confirmation request and nothing else, and may CLEAR.

    "Please confirm future payments should go to ALT", "confirm we should change
    the payment destination to ALT" and "please confirm future payments will be
    sent to ALT" ask for confirmation and issue an instruction in the same
    breath. The confirmation framing does not make the instruction go away, and
    treating these as confirmation of the *current* destination would let a
    steered model relabel a routing request and clear it.

    The instruction test is the same shared action layer I5 uses, so the two
    cannot disagree: if the floor would flag the destination, the confirmation
    verdict is not accepted either.
    """
    if not (quote or "").strip():
        return False
    if not CONFIRMATION_PHRASE.search(quote):
        return False
    return not has_live_change_or_routing_action(quote)


def change_act_detected(norm_text: str) -> bool:
    """I3 support. Is there deterministic change language about a payment field?

    Deliberately crude: a change verb and a payment noun inside one sentence.
    It is only ever used to *escalate*, never to clear, so a crude detector
    costs review time but never costs safety.
    """
    for sentence in SENTENCE_SPLIT.split(norm_text or ""):
        if not sentence.strip():
            continue
        if CHANGE_WORD.search(sentence) and ENTITY_WORD.search(sentence):
            return True
    return False


def unverifiable_finding(reason: str) -> Finding:
    return Finding(
        code="I3_UNVERIFIABLE_REQUEST",
        severity="hold",
        message=reason,
        independent_of_model=True,
    )


def authentication_findings(email: dict) -> list[Finding]:
    """Informational only. Passing mail auth is not evidence of a safe change."""
    out: list[Finding] = []
    auth = email.get("auth", {}) or {}
    failed = [k.upper() for k, v in auth.items() if str(v).lower() not in ("pass", "none")]
    if failed:
        out.append(
            Finding(
                code="AUTH_FAILED",
                severity="info",
                message="Mail authentication failed: " + ", ".join(failed),
                independent_of_model=True,
            )
        )
    reply_to = (email.get("reply_to") or "").lower()
    sender = (email.get("from") or "").lower()
    m_from = re.search(r"@([\w.\-]+)", sender)
    m_reply = re.search(r"@([\w.\-]+)", reply_to)
    if m_from and m_reply and m_from.group(1) != m_reply.group(1):
        out.append(
            Finding(
                code="REPLY_TO_DOMAIN_MISMATCH",
                severity="info",
                message=f"Reply-To domain {m_reply.group(1)} differs from sender domain {m_from.group(1)}.",
                independent_of_model=True,
            )
        )
    return out
