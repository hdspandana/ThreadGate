"""Unit tests for the deterministic action-to-destination association layer.

`actions.py` exists because a windowed negation check is not a security
boundary. It could not tell the difference between

    "Do not route to the old account; route future payments to ALT."

where the negation is spent on the first clause and ALT is live, and

    "Do not route payments to ALT."

where ALT is named only to be refused. Both had a negation within N
characters of the routing verb, so both were suppressed - and the first is a
live bypass.

These tests pin the polarity rule that replaced it: a cue binds to the next
verb, and a comma or a clause boundary in between means it was spent on
whatever came first.
"""

import pytest

from threadgate.actions import (
    find_actions,
    has_live_action,
    has_live_change_action,
    has_live_change_or_routing_action,
    live_destination_links,
)
from threadgate.normalize import normalize_text
from threadgate.tokens import find_tokens

ALT = "50100234558812"



def links(text: str):
    """Destination links for a text, via the same token path the pipeline uses."""
    return live_destination_links(text, find_tokens(normalize_text(text)))


# ---------------------------------------------------------------------------
# The polarity rule
# ---------------------------------------------------------------------------


class TestPolarityBindsToTheNextVerb:
    """A cue governs the next verb unless punctuation intervenes."""

    def test_a_plain_negation_suppresses_the_action_it_precedes(self):
        actions = find_actions("Do not route payments to ALT.")
        assert [a.negated for a in actions] == [True]
        assert not any(a.live for a in actions)

    def test_a_negation_does_not_reach_across_a_semicolon(self):
        """The bypass that motivated the whole layer.

        One sentence, two clauses. The negation belongs to the first.
        """
        text = "Do not route to the old account; route future payments to ALT."
        actions = find_actions(text)
        negated = [a for a in actions if a.negated]
        live = [a for a in actions if a.live]
        assert len(negated) == 1
        assert text[negated[0].start : negated[0].end] == "route to"
        assert len(live) == 1
        assert live[0].start > negated[0].end

    def test_a_negation_does_not_reach_across_a_comma(self):
        text = "Instead of the current account, route future payments to ALT."
        assert has_live_action(text)

    def test_a_negation_does_not_reach_across_but(self):
        text = "Ignore the previous request, but route future payments to ALT."
        assert has_live_action(text)

    def test_a_negation_still_suppresses_when_nothing_intervenes(self):
        for text in (
            "Do not route payments to ALT.",
            "Please do not send payments to ALT.",
            "Never transfer funds to ALT.",
            "We are not changing our bank details.",
            "Nothing is changing today.",
        ):
            assert not has_live_action(text), text

    def test_a_conditional_is_not_an_instruction(self):
        """'Let us know if anything needs correcting' names a possibility.

        The change verb is real, which is why conditionality is a separate axis
        from negation rather than another entry in the negation vocabulary.
        """
        assert not has_live_change_action("Let us know if anything needs correcting.")
        assert has_live_change_action("Please correct the beneficiary name.")

    def test_correct_used_as_an_adjective_is_not_an_action(self):
        """The one genuine confirmation case in the frozen set says 'correct'.

        A bare `correct` stem in the change vocabulary used to reject it.
        """
        assert not has_live_change_action(
            "Can you confirm you have our correct bank details on file?"
        )


# ---------------------------------------------------------------------------
# Action kinds
# ---------------------------------------------------------------------------


class TestActionVocabulary:
    @pytest.mark.parametrize(
        "text",
        [
            "Route future payments to ALT.",
            "Please use account ALT for future payments.",
            "Please make all future payments to account ALT.",
            "All future payments should go to account ALT.",
            "Future payments will be sent to account ALT.",
            "Payments are to go to account ALT.",
            "Please set account ALT as the destination for future payments.",
            "For future payments, use ALT.",
            "Please make ALT the payment destination.",
            "Please confirm future payments should go to account ALT.",
            "Can you confirm that we should pay future invoices to ALT?",
            "Instead of the current account, route future payments to ALT.",
            "Do not route to the old account; route future payments to ALT.",
            "Ignore the previous request, but route future payments to ALT.",
        ],
    )
    def test_every_known_bypass_produces_a_live_action(self, text):
        """The 14 constructions from the audit. None may slip through the layer."""
        assert has_live_action(text.replace("ALT", ALT)), text

    @pytest.mark.parametrize(
        "text",
        [
            "ALT is one of our pre-registered accounts.",
            "For reference, ALT is our older account.",
            "Our records show ALT was used until last year.",
        ],
    )
    def test_a_bare_mention_produces_no_action(self, text):
        """Mentioning an alternate must not by itself engage the floor."""
        assert not has_live_action(text.replace("ALT", ALT)), text

    def test_a_destination_is_bound_to_the_action_that_governs_it(self):
        text = f"Please use account {ALT} for future payments."
        found = links(text)
        assert len(found) == 1
        link = found[0]
        assert link.token_start < link.token_end
        assert text[link.token_start : link.token_end] == ALT
        assert link.action.end <= link.token_start
        assert not link.negated

    def test_a_refused_destination_produces_no_link(self):
        text = f"Do not route payments to {ALT}."
        assert links(text) == []

    def test_a_corrected_instruction_produces_one_link_for_the_live_clause(self):
        text = f"Do not route to the old account; route future payments to {ALT}."
        found = links(text)
        assert len(found) == 1
        assert text[found[0].token_start : found[0].token_end] == ALT
        assert not found[0].negated


# ---------------------------------------------------------------------------
# The change vocabulary, shared by I2b and I2c
# ---------------------------------------------------------------------------


class TestChangeVocabulary:
    @pytest.mark.parametrize(
        "text",
        [
            "Please update our beneficiary name; no new bank details are needed.",
            "Our bank details are unchanged. However, please amend the beneficiary name on file.",
            "No change to the account number, but please redirect payments to our new remittance desk.",
            "Nothing else has changed; just make sure the payee name is corrected on your side.",
            "Please route future payments to ALT; our details are unchanged.",
        ],
    )
    def test_a_change_hidden_behind_a_no_change_phrase_is_detected(self, text):
        assert has_live_change_or_routing_action(text), text

    @pytest.mark.parametrize(
        "text",
        [
            "We are not changing our bank details.",
            "Our bank details are unchanged.",
            "Nothing is changing today, this is just a reminder about the invoice due date.",
            "As discussed on the call just now, there are no changes to the account for Q4.",
            "Your payment details are unchanged: A/C 50100234554455, IFSC HDFC0001234.",
            "They have not changed since we onboarded.",
            "Do NOT change our bank details - phishing alert",
        ],
    )
    def test_a_genuine_no_change_statement_is_not_read_as_a_change(self, text):
        """The over-correction this layer must not make.

        Making every message containing 'unchanged' a HOLD would be a bug, not
        a defence: these are the benign cases the gate must still clear.
        """
        assert not has_live_change_or_routing_action(text), text
