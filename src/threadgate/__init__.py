"""ThreadGate - an action-level gate for payment-detail change requests.

AI interprets the email. Code verifies the change against the record. A human
attests before anything executes.

The AI is never trusted with the verdict. See policy.py for the monotone
decision rule and invariants.py for the checks that do not consult the model.
"""

__version__ = "0.1.0"
