"""Freshness boundaries; synthetic records only, no provider calls."""
import copy
from datetime import date, timedelta
import uuid
import pytest
from threadgate.attestation import VerificationEvent
from threadgate.clock import fixed
from threadgate.pipeline import run_case
from threadgate.reference import reference_state
from threadgate.records import load_cases
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Negative age is invalid, age zero and the configured boundary are current.
AGES = [(-1, 'STALE'), (0, 'CURRENT'), (90, 'CURRENT'), (91, 'STALE'),
        (None, 'STALE'), ('invalid', 'STALE'), ('missing-destination', 'MISSING')]


def investigation(vendors, age, change=True):
    vendors = copy.deepcopy(vendors)
    case = copy.deepcopy(load_cases(ROOT/'data/cases/frozen_v1.json')[0])
    if not change:
        case['email'] = {'body': 'No change to our payment details.', 'subject': '', 'from': ''}
    vendor = vendors[case['vendor_id']]
    if age == 'missing-destination':
        # Missing destination wins even over an invalid future confirmation.
        from threadgate.records import FIELD_PATHS
        from threadgate.reference import DESTINATION_REFERENCE_FIELDS
        for field in DESTINATION_REFERENCE_FIELDS:
            path = FIELD_PATHS.get(field)
            if path:
                vendor.data[path[0]][path[1]] = None
        age = -1
    vendor.data['reference_freshness_days'] = 90
    vendor.data['reference_updated_at'] = (None if age is None else 'invalid' if age == 'invalid'
        else (date(2026, 10, 6)-timedelta(days=age)).isoformat())
    return run_case(case, vendors, extractor_mode='offline', clock=fixed('2026-10-06')), vendor


@pytest.mark.parametrize('age,state', AGES)
@pytest.mark.parametrize('change', [True, False])
def test_reference_date_policy_boundaries(vendors, age, state, change):
    result, vendor = investigation(vendors, age, change)
    assert reference_state(vendor, fixed('2026-10-06')) == state
    assert result.decision.reference_state == state
    if change:
        assert result.decision.decision == 'HOLD'
    else:
        assert result.decision.decision == ('CLEAR' if state == 'CURRENT' else 'REVIEW')
    assert any(f.code == 'R_MISSING_REFERENCE' for f in result.decision.findings) == (state == 'MISSING')
    assert any(f.code == 'R_STALE_REFERENCE' for f in result.decision.findings) == (state == 'STALE')


@pytest.mark.parametrize('age,state', AGES)
def test_reference_date_attestation_eligibility(vendors, tmp_path, age, state):
    # This exercises the real transactional service when its dependency exists.
    pytest.importorskip('pyotp')
    from threadgate.workspace import Workspace, Conflict
    result, _ = investigation(vendors, age)
    service = Workspace(tmp_path/'dates.db', require_mfa=False)
    password = 'synthetic-only-long-password'
    service.bootstrap('owner', password)
    admin = service.login('owner', password)
    tokens = {}
    for role in ('analyst', 'verifier'):
        service.create_user(admin, role, password, role)
        tokens[role] = service.login(role, password)
    case_id = service.submit(tokens['analyst'], result)
    service.assign(tokens['analyst'], case_id, 'verifier', 1)
    c = result.verification
    event = VerificationEvent(str(uuid.uuid4()), c.vendor_id, c.request_id,
        c.destination_digest, c.reference_version, 'verifier', 'now',
        request_digest=c.request_digest, reference_digest=c.reference_digest)
    args = (tokens['verifier'], case_id, 2, event, c, True, True,
            result.decision.reference_state == 'CURRENT')
    if state == 'CURRENT':
        assert service.verify(*args).accepted
        assert service.get_case(admin, case_id)['state'] == 'VERIFIED'
    else:
        with pytest.raises(Conflict):
            service.verify(*args)
        assert service.get_case(admin, case_id)['state'] == 'ASSIGNED'
        assert not service.export_case(admin, case_id)['verification_events']
