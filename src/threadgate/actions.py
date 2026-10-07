"""A small deterministic action-to-destination association layer.

Three questions keep coming up in different places, and answering them three
different ways is how the gate got holes:

  I5   does this email *act* on a payment destination, or merely mention one?
  I2b  does this quote say nothing is changing, or does it change something?
  I2c  is this a request to confirm what is on file, or to confirm a change?

They are the same question: **what action is being applied to which
destination, and with what polarity.** One layer answers it, and the three
invariants read from it.

Why polarity has to be *associated* rather than *detected*
--------------------------------------------------------
A negation that is merely found in a window suppresses everything after it.
That is wrong in both directions:

  "Do not route to the old account; route future payments to ALT."
      - one clause negated, one live. A windowed check kills the live one.

  "Instead of the current account, route future payments to ALT."
      - "Instead of" attaches to *the current account*, not to the routing.
        A windowed check kills the only instruction in the sentence.

So a cue binds to the next verb, but a comma or a clause boundary between the
cue and that verb means the cue was consumed by whatever came first. "Instead
of the current account, route" - the cue is spent on the noun phrase before the
comma, and the routing stands.

Deliberately small: three action patterns, one clause splitter, one polarity
rule. Not a growing pile of unrelated regexes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# --- vocabulary -----------------------------------------------------------
# Payment-flow nouns. Their presence is what separates "use ALT" (an
# instruction) from "ALT is on file" (a mention).
PAYMENT_NOUN = (
    r"(?:payments?|remittances?|invoices?|funds?|proceeds?|collections?|"
    r"payouts?|disbursements?|amounts?|money|transfers?|credits?|debits?|"
    r"salaries?|fees?|dues|receivables?|payables?|cycles?|quarters?)"
)

# Things that can be a payment destination.
DEST_NOUN = (
    r"(?:account|a\s*/\s*c|acct|ac|ifsc|iban|swift|beneficiary|destination|"
    r"bank\s+details?|bank|branch|payee)"
)

# Verbs that move money somewhere. Used with a directional complement.
TRANSFER_VERB = (
    r"(?:route|routing|remit|remitting|send|sending|transfer|transferring|"
    r"pay|paying|direct|directing|switch|switching|move|moving|credit|"
    r"crediting|deposit|depositing|forward|forwarding|channel|channelling|"
    r"channeling|disburse|disbursing|wire|wiring|post|posting|make|making|"
    r"change|changing|update|updating|redirect|redirecting|amend|amending|"
    r"revise|revising|replace|replacing)"
)

# The flow verb in "payments should go to X", "payments will be sent to X".
FLOW_VERB = (
    r"(?:go|going|gone|sent|routed|directed|credited|transferred|remitted|"
    r"disbursed|posted|made|paid|applied|moved|forwarded|channelled|channeled)"
)
MODAL = (
    r"(?:should|will|shall|must|would|can|could|are\s+to|is\s+to|are|is|be|"
    r"been|being|am|were|was|to)"
)
DIRECTIONAL = r"(?:to|into|onto|towards?|toward)"

# Verbs that assign a destination directly, with no preposition.
ASSIGN_VERB = (
    r"(?:use|using|utilise|utilize|set|setting|designate|designating|"
    r"nominate|nominating|select|selecting|choose|choosing|appoint|"
    r"appointing|apply|applying|keep|keeping|make|making)"
)

# A filler token between parts of an action phrase: a word, possibly with an
# apostrophe, currency symbol or separator inside it.
_W = r"[\w'’.,$£€/-]+"

# --- the three action patterns -------------------------------------------
# F1: a transfer verb with a directional complement.
#     "route future payments to", "remit to", "make all future payments to",
#     "should pay future invoices to"
F1_TRANSFER = re.compile(
    rf"\b{TRANSFER_VERB}\b(?:\s+{_W}){{0,5}}?\s*\b{DIRECTIONAL}\b",
    re.IGNORECASE,
)

# F2: a payment subject with a modal and a flow verb.
#     "all future payments should go to", "future payments will be sent to",
#     "payments are to go to"
F2_FLOW = re.compile(
    rf"\b{PAYMENT_NOUN}\b(?:\s+{_W}){{0,4}}?\s*\b{MODAL}\b"
    rf"(?:\s+{_W}){{0,3}}?\s*\b{FLOW_VERB}\b(?:\s+{_W}){{0,3}}?\s*\b{DIRECTIONAL}\b",
    re.IGNORECASE,
)

# F3: an assignment verb acting directly on a destination. Needs a payment
#     noun in the clause, or "use ALT" would fire on any sentence that happens
#     to use something.
#     "use account ALT for future payments", "set ALT as the destination",
#     "make ALT the payment destination"
F3_ASSIGN = re.compile(
    rf"\b{ASSIGN_VERB}\b",
    re.IGNORECASE,
)

# Verbs that change something. No directional complement is required, because
# "update our beneficiary name" changes a payment field without saying where
# anything goes.
#
# `correct` is absent from the stem list on purpose and gets its own pattern
# below, because it is the one change verb that doubles as an adjective.
# "our correct bank details" is a noun phrase; "correct the beneficiary name"
# is an instruction. The bare stem cannot tell them apart, so the stem is not
# used and a determiner is required instead.
CHANGE_VERB = (
    r"(?:updat\w*|chang\w*|amend\w*|revis\w*|replac\w*|modif\w*|"
    r"corrected|correcting|correction|switch\w*|transfer\w*|convert\w*|"
    r"renamed|renaming)"
)
F4_CHANGE = re.compile(rf"\b{CHANGE_VERB}\b", re.IGNORECASE)

# `correct` as a verb: it governs a following determiner. "correct the
# beneficiary name", "correct our records", "correct this account". The
# adjectival use - "our correct bank details", "the correct account" - is not
# followed by a determiner, so it does not match.
CORRECT_VERB = re.compile(
    r"\bcorrect(?=\s+(?:the|our|your|their|this|these|those|a|an|any|all|it|"
    r"them|his|her|its)\b)",
    re.IGNORECASE,
)

# Words that reverse an instruction.
NEGATION_CUE = re.compile(
    r"\b(?:not|n't|never|nothing|no|no\s+longer|instead\s+of|rather\s+than|"
    r"avoid|disregard|ignore|cancel|cancelling|canceling|withdraw|withdrawing|"
    r"revert|reverting|stop|superseded|abandon|without)\b",
    re.IGNORECASE,
)

# A conditional is not an instruction. "Let us know if anything needs
# correcting" names a possible future correction; it does not make one. The
# change verb is real, which is why this is a separate axis from negation
# rather than another entry in the negation vocabulary.
CONDITIONAL_CUE = re.compile(
    r"\b(?:if|unless|in\s+case|should\s+(?:it|anything|you)|were\s+(?:it|anything)|"
    r"whether|whenever)\b",
    re.IGNORECASE,
)

# Clause boundaries. A negation does not cross one: whatever it applied to on
# the left is settled, and what follows is a fresh instruction.
CLAUSE_SPLIT = re.compile(r"[;]|\bbut\b", re.IGNORECASE)

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class Action:
    """One action phrase, with the polarity attached to it."""

    kind: str  # transfer | flow | assign | change
    start: int  # offsets within the text handed to find_actions
    end: int
    negated: bool
    conditional: bool = False

    @property
    def span(self) -> tuple[int, int]:
        return (self.start, self.end)

    @property
    def live(self) -> bool:
        """Does this action actually instruct?

        Negated actions instruct the opposite. Conditional ones instruct
        nothing - they describe a possibility.
        """
        return not self.negated and not self.conditional


@dataclass(frozen=True)
class RoutingLink:
    """An action bound to a destination token, with the action's polarity."""

    action: Action
    token_start: int
    token_end: int
    distance: int
    token: object = None  # the Token, carried so callers need not re-find it

    @property
    def negated(self) -> bool:
        return self.action.negated


def _cue_applies(clause: str, action_start: int, cue) -> bool:
    """Does this cue govern the action at this offset?

    Shared by negation and conditionality: a cue binds to the next verb, but a
    comma or a clause boundary in between means it was spent on whatever came
    first.
    """
    for m in cue.finditer(clause):
        if m.start() >= action_start:
            break
        if not re.search(r"[,;]", clause[m.end(): action_start]):
            return True
    return False


def _is_negated(clause: str, action_start: int) -> bool:
    """Is there an unspent negation cue governing the action at this offset?

    A cue binds to the next verb. But if a comma or a clause boundary sits
    between them, the cue was already spent on whatever came before it - which
    is what separates

        "Instead of the current account, route payments to ALT"   (live)
    from
        "Do not route payments to ALT"                            (negated)

    Both contain a cue before the verb. Only one comma does.
    """
    return _cue_applies(clause, action_start, NEGATION_CUE)


def _clauses(text: str) -> list[tuple[int, str]]:
    """Offset, clause-text pairs. Negation and association stay inside one."""
    out: list[tuple[int, str]] = []
    pos = 0
    for m in CLAUSE_SPLIT.finditer(text):
        out.append((pos, text[pos: m.start()]))
        pos = m.end()
    out.append((pos, text[pos:]))
    return [(o, c) for o, c in out if c.strip()]


def find_actions(text: str) -> list[Action]:
    """Every payment-destination action in one sentence, with polarity.

    Offsets are relative to `text`. Overlapping matches are collapsed to the
    widest, so "make all future payments to" is one action rather than two.
    """
    actions: list[Action] = []
    for offset, clause in _clauses(text or ""):
        found: list[tuple[int, int, str]] = []
        for kind, pattern in (
            ("transfer", F1_TRANSFER),
            ("flow", F2_FLOW),
            ("change", F4_CHANGE),
            # Run alongside F4 rather than folded into its alternation,
            # because this one needs a lookahead the stem list cannot express.
            ("change", CORRECT_VERB),
        ):
            for m in pattern.finditer(clause):
                found.append((offset + m.start(), offset + m.end(), kind))
        # F3 is an assignment verb with a payment noun somewhere in the clause.
        if re.search(PAYMENT_NOUN, clause, re.IGNORECASE):
            for m in F3_ASSIGN.finditer(clause):
                found.append((offset + m.start(), offset + m.end(), "assign"))
        if not found:
            continue
        found.sort(key=lambda t: (t[0], -(t[1] - t[0])))
        for start, end, kind in found:
            actions.append(
                Action(
                    kind=kind,
                    start=start,
                    end=end,
                    negated=_is_negated(clause, start - offset),
                    conditional=_cue_applies(
                        clause, start - offset, CONDITIONAL_CUE
                    ),
                )
            )
    return _collapse(actions)


def _collapse(actions: list[Action]) -> list[Action]:
    """Drop actions contained in a wider one; keep first on a tie."""
    out: list[Action] = []
    for a in sorted(actions, key=lambda x: (x.start, -x.end)):
        if any(o.start <= a.start and a.end <= o.end for o in out):
            continue
        out.append(a)
    return sorted(out, key=lambda x: x.start)


def has_live_action(text: str, kinds: set[str] | None = None) -> bool:
    """Is there an action in this text that is not negated?"""
    return any(
        a.live and (kinds is None or a.kind in kinds)
        for a in find_actions(text)
    )


def has_live_change_action(text: str) -> bool:
    """A change instruction that is not negated.

    Used to catch a quote that says nothing is changing in one clause while
    instructing a change in another - "update our beneficiary name; no new bank
    details are needed". The negation handling is what keeps "we are not
    changing our bank details" and "nothing is changing today" valid.
    """
    return any(a.kind == "change" and a.live for a in find_actions(text))


def has_live_change_or_routing_action(text: str) -> bool:
    """A live change, or a live instruction about where money should go."""
    return any(
        a.kind in ("change", "transfer", "flow") and a.live
        for a in find_actions(text)
    )


def link_actions_to_destinations(
    text: str, tokens, max_distance: int = 140
) -> list[RoutingLink]:
    """Bind each action to the destination token it governs.

    The destination follows its action - you name where money goes after you
    say it is going - so a token is only linked if it starts at or after the
    action and is close enough to be its object rather than a neighbouring
    detail. A link is never searched backwards: "Do not use ALT; we will
    continue to remit to CUR" must not bind ALT to the live instruction.
    """
    links: list[RoutingLink] = []
    for a in find_actions(text):
        for tok in tokens:
            if tok.start < a.end:
                continue
            distance = tok.start - a.end
            if distance > max_distance:
                continue
            links.append(
                RoutingLink(
                    action=a,
                    token_start=tok.start,
                    token_end=tok.end,
                    distance=distance,
                    token=tok,
                )
            )
    # Nearest destination to each action wins.
    best: dict[tuple[int, int], RoutingLink] = {}
    for link in links:
        key = (link.action.start, link.action.end)
        if key not in best or link.distance < best[key].distance:
            best[key] = link
    return sorted(best.values(), key=lambda l: l.action.start)


def live_destination_links(text: str, tokens, max_distance: int = 140):
    """Links whose action is not negated - the ones that actually instruct."""
    return [l for l in link_actions_to_destinations(text, tokens, max_distance)
            if not l.negated]
