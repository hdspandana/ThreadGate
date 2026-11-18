"""Execute actual UI control-flow ASTs with mocked UI/provider boundaries.

No Streamlit, dotenv, OTP dependency or provider is needed for these isolated
regressions. This does not replace AppTest/browser integration coverage.
"""
import ast
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest

ROOT = Path(__file__).resolve().parents[1]


class State(dict):
    def __getattr__(self, name):
        return self[name]

    def __setattr__(self, name, value):
        self[name] = value


class Conflict(Exception):
    pass


def tree(path):
    return ast.parse((ROOT/path).read_text())


def execute(nodes, namespace):
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual-ui-code>', 'exec'), namespace)


def configured_predicate():
    module = tree('src/threadgate/config.py')
    nodes = [n for n in module.body if isinstance(n, ast.FunctionDef)
             and n.name in {'is_configured', 'key_configured'}]
    namespace = {'os': os, 'PLACEHOLDERS': next(ast.literal_eval(n.value) for n in module.body
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'PLACEHOLDERS' for t in n.targets))}
    execute(nodes, namespace)
    return namespace['key_configured']


@pytest.mark.parametrize('gemini,google,allowed', [
    ('synthetic-test-key', None, True), (None, 'synthetic-test-key', True),
    ('placeholder', 'synthetic-test-key', True), ('synthetic-test-key', 'xxxx', True),
    (None, None, False), ('placeholder', None, False), (None, 'your-key-here', False),
    ('  ', '<replace-me>', False), ('changeme', 'xxxx', False), ('PLACEHOLDER', None, False),
    (None, 'your_key_here', False), ('', '', False),
    ('synthetic-test-key', 'another-synthetic-key', True),
])
@pytest.mark.parametrize('app', ['product', 'workbench'])
def test_ui_supported_key_guards(monkeypatch, gemini, google, allowed, app):
    for key, value in [('GEMINI_API_KEY', gemini), ('GOOGLE_API_KEY', google)]:
        monkeypatch.delenv(key, raising=False)
        if value is not None:
            monkeypatch.setenv(key, value)
    predicate = configured_predicate()
    assert predicate() == allowed
    module = tree(f'app/{app}.py')
    assert any(isinstance(n, ast.ImportFrom) and n.module == 'threadgate.config'
               and any(a.name == 'key_configured' for a in n.names) for n in module.body)
    st = MagicMock()
    st.session_state = State()
    provider = MagicMock(return_value=SimpleNamespace(decision=SimpleNamespace(attestation_required=True)))
    namespace = dict(st=st, time=SimpleNamespace(monotonic=lambda: 100), os=os,
        key_configured=predicate, run_case=provider, Conflict=Conflict, vendors={}, case={},
        selected_mode='gemini', identity='synthetic')
    if app == 'product':
        node = next(n for n in module.body if isinstance(n, ast.FunctionDef) and n.name == 'inspect')
        execute([node], namespace)
        if allowed:
            namespace['inspect']({}, 'gemini')
        else:
            with pytest.raises(Conflict):
                namespace['inspect']({}, 'gemini')
    else:
        node = next(n for n in module.body if isinstance(n, ast.If)
                    and isinstance(n.test, ast.Call) and isinstance(n.test.func, ast.Attribute)
                    and n.test.func.attr == 'button' and n.test.args
                    and isinstance(n.test.args[0], ast.Constant) and n.test.args[0].value == '◈  Inspect request')
        execute([node], namespace)
        assert st.error.called == (not allowed)
    assert provider.call_count == int(allowed)


@pytest.mark.parametrize('return_case', [False, True])
def test_removed_vendor_preserves_product_recovery_and_history(return_case):
    module = tree('app/product.py')
    # Execute the actual verifier branch AND its following history/export nodes.
    expected = ast.dump(ast.parse("principal.role=='verifier' and record['state']=='ASSIGNED' and record['assigned_to']==principal.username", mode='eval').body)
    nodes = None
    for parent in ast.walk(module):
        for _, body in ast.iter_fields(parent):
            if not isinstance(body, list):
                continue
            for index, node in enumerate(body):
                if isinstance(node, ast.If) and ast.dump(node.test) == expected:
                    nodes = body[index:]
    assert nodes is not None, 'Actual verifier branch not located'
    st = MagicMock()
    st.session_state = State(verification_preview=('old', 'must not reuse'))
    st.button.side_effect = lambda label, **kw: return_case and label.startswith('Return for reinvestigation')
    class Rerun(Exception):
        pass
    st.rerun.side_effect = Rerun
    service = MagicMock()
    draft = MagicMock(side_effect=AssertionError('Missing reference must not start reinspection'))
    namespace = dict(st=st, principal=SimpleNamespace(role='verifier', username='verifier'),
        record=dict(state='ASSIGNED', assigned_to='verifier', vendor_id='removed', revision=2, created_by='analyst'),
        report={'extractor':'offline'}, vendors={}, service=service, token='synthetic-token', case_id='synthetic-case',
        draft_input=draft, json=__import__('json'), inspect=MagicMock(), reveal=False)
    service.audit.return_value = []
    service.export_case.return_value = {'synthetic':True}
    if return_case:
        with pytest.raises(Rerun):
            execute(nodes, namespace)
        service.return_for_reinvestigation.assert_called_once_with('synthetic-token','synthetic-case',2)
    else:
        execute(nodes, namespace)
        assert st.warning.called
        assert 'verification_preview' not in st.session_state
        service.audit.assert_called_once_with('synthetic-token','synthetic-case')
        service.export_case.assert_called_once_with('synthetic-token','synthetic-case')
        assert st.download_button.call_count == 2
        assert not st.error.called
    service.verify.assert_not_called()
    draft.assert_not_called()
    namespace['inspect'].assert_not_called()


@pytest.mark.parametrize('path',['compose.yaml','deployment/compose.public.yaml'])
def test_compose_propagates_both_supported_api_keys_without_values(path,capsys):
    import yaml
    text=(ROOT/path).read_text()
    environment=yaml.safe_load(text)['services']['app']['environment']
    for name in ('GEMINI_API_KEY','GOOGLE_API_KEY'):
        assert environment[name]=='${'+name+':-}'
    assert capsys.readouterr().out==''
