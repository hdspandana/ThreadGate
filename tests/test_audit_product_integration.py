"""Real AppTest regression, retained for an installed runtime; never calls AI."""
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]


def test_removed_vendor_real_product_reinvestigation(tmp_path, monkeypatch):
    pytest.importorskip('pyotp')
    pytest.importorskip('dotenv')
    pytest.importorskip('streamlit')
    from streamlit.testing.v1 import AppTest
    from threadgate.workspace import Workspace
    from threadgate.pipeline import run_case
    from threadgate.clock import fixed
    from threadgate import records
    monkeypatch.setenv('THREADGATE_REQUIRE_MFA', '0')
    service = Workspace(tmp_path/'product.db')
    password = 'synthetic-only-long-password'
    service.bootstrap('owner', password)
    owner = service.login('owner', password)
    for role in ('analyst', 'verifier'):
        service.create_user(owner, role, password, role)
    vendors = records.load_vendors(ROOT/'data/records/vendor_master.json')
    case = records.load_cases(ROOT/'data/cases/frozen_v1.json')[0]
    result = run_case(case, vendors, extractor_mode='offline', clock=fixed('2026-10-06'))
    analyst = service.login('analyst', password)
    case_id = service.submit(analyst, result)
    service.assign(analyst, case_id, 'verifier', 1)
    monkeypatch.setenv('THREADGATE_WORKSPACE_DB', service.path)
    monkeypatch.setenv('THREADGATE_SKIP_DOTENV', '1')
    monkeypatch.setattr(records, 'load_vendors', lambda path: {})
    app = AppTest.from_file(str(ROOT/'app/product.py'))
    app.session_state['workspace_token'] = service.login('verifier', password)
    app.run(timeout=30)
    assert not app.exception and not app.error
    assert any('Trusted vendor record unavailable' in w.value for w in app.warning)
    assert not any(b.label == 'Re-inspect and record attestation' for b in app.button)
    assert app.dataframe  # Inbox and case audit remain rendered.
    next(b for b in app.button if b.label.startswith('Return for reinvestigation')).click().run()
    assert not app.exception and not app.error
    assert service.get_case(owner, case_id)['state'] == 'NEEDS_REINVESTIGATION'
