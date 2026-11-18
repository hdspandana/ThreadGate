"""Durability, concurrency, privacy and workbench smoke regressions."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
import sqlite3
import pytest
from threadgate.attestation import VerificationContext, VerificationEvent
from threadgate.durable import SQLiteAttestationStore
from threadgate.reporting import case_report
from threadgate.pipeline import run_case
from threadgate.records import load_cases, load_vendors

ROOT = Path(__file__).resolve().parents[1]
CTX = VerificationContext('vendor', 'request', 'digest', 'v1')
EVENT = VerificationEvent('event', 'vendor', 'request', 'digest', 'v1')


def test_replay_survives_store_restart(tmp_path):
    path = tmp_path / 'events.db'
    assert SQLiteAttestationStore(path).consume(EVENT, CTX).accepted
    assert SQLiteAttestationStore(path).consume(EVENT, CTX).code == 'ATTESTATION_REPLAY'


def test_concurrent_consumption_accepts_exactly_once(tmp_path):
    path = tmp_path / 'events.db'
    SQLiteAttestationStore(path)
    def consume(_):
        return SQLiteAttestationStore(path).consume(EVENT, CTX).accepted
    with ThreadPoolExecutor(max_workers=8) as workers:
        assert sum(workers.map(consume, range(16))) == 1


@pytest.mark.parametrize('field,value', [('vendor_id','other'), ('request_id','other'),
    ('destination_digest','other'), ('reference_version','v2')])
def test_rejected_binding_is_durably_burned(tmp_path, field, value):
    store = SQLiteAttestationStore(tmp_path / 'events.db')
    assert not store.consume(EVENT, replace(CTX, **{field:value})).accepted
    assert store.consume(EVENT, CTX).code == 'ATTESTATION_REPLAY'


def test_not_required_does_not_consume(tmp_path):
    store = SQLiteAttestationStore(tmp_path / 'events.db')
    assert not store.consume(EVENT, CTX, required=False).consumed
    assert len(store) == 0


def test_empty_id_does_not_consume(tmp_path):
    store = SQLiteAttestationStore(tmp_path / 'events.db')
    assert not store.consume(replace(EVENT, event_id=''), CTX).consumed
    assert len(store) == 0


def test_storage_error_does_not_return_acceptance(tmp_path):
    store = SQLiteAttestationStore(tmp_path / 'events.db')
    with sqlite3.connect(store.path) as db:
        db.execute('DROP TABLE consumed_events')
    with pytest.raises(sqlite3.OperationalError):
        store.consume(EVENT, CTX)


def test_report_omits_destination_values_and_email():
    vendors = load_vendors(ROOT / 'data/records/vendor_master.json')
    case = load_cases(ROOT / 'data/cases/frozen_v1.json')[0]
    result = run_case(case, vendors, extractor_mode='offline')
    report = case_report(result, 'DEMO_RECORDED')
    assert report['gate_decision'] == result.decision.decision
    assert report['workflow_status'] == 'DEMO_RECORDED'
    import json
    text = json.dumps(report)
    assert case['email']['body'] not in text
    assert vendors[case['vendor_id']].current('account_number') not in text


def test_pasted_request_ids_change_with_body():
    from threadgate.attestation import request_id_for
    assert request_id_for({'email':{'body':'first'}}) != request_id_for({'email':{'body':'second'}})


def test_workbench_initial_load():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(ROOT / 'app/workbench.py')).run(timeout=30)
    assert not app.exception
    assert any('Inspect request' in button.label for button in app.button)


def test_workbench_offline_inspection(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv('THREADGATE_DB', str(tmp_path / 'ui.db'))
    app = AppTest.from_file(str(ROOT / 'app/workbench.py')).run(timeout=30)
    next(b for b in app.button if 'Inspect request' in b.label).click().run(timeout=30)
    assert not app.exception
    assert len(app.metric) == 4
    for checkbox in app.checkbox:
        checkbox.check()
    app.run()
    next(b for b in app.button if b.label == 'Record synthetic verification').click().run()
    assert not app.exception
    assert app.session_state['workflow'] == 'DEMO_RECORDED'
    next(b for b in app.button if b.label == 'Test replay of the same event').click().run()
    assert not app.exception
    assert any('ATTESTATION_REPLAY' in item.value for item in app.info)


def test_workbench_attack_lab():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(ROOT / 'app/workbench.py')).run(timeout=30)
    app.sidebar.radio[0].set_value('Attack Lab').run(timeout=30)
    next(b for b in app.button if 'Inspect request' in b.label).click().run(timeout=30)
    assert not app.exception


def test_workbench_evaluation_page():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(ROOT / 'app/workbench.py')).run(timeout=30)
    app.sidebar.radio[0].set_value('Evaluation').run(timeout=30)
    assert not app.exception
