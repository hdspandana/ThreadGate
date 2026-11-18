"""Executed rendering/control-flow checks; no Streamlit/browser substitution claims."""
import ast
import importlib.util
from pathlib import Path
import re
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from threadgate.presentation import decision_banner_html

ROOT=Path(__file__).resolve().parents[1]


class State(dict):
    def __getattr__(self,name):return self[name]
    def __setattr__(self,name,value):self[name]=value


def execute(node,namespace):
    exec(compile(ast.Module(body=[node],type_ignores=[]),'<actual-demo-ui>','exec'),namespace)


@pytest.mark.parametrize('decision',['CLEAR','REVIEW','HOLD'])
def test_decision_banner_has_textual_status_and_no_payment_approval(decision):
    rendered=decision_banner_html(decision)
    assert f'aria-label="{decision} gate decision"' in rendered
    assert 'role="status"' in rendered and f'<strong>{decision}</strong>' in rendered
    if decision=='CLEAR':assert 'Not a guarantee of safety, payment approval' in rendered
    elif decision=='REVIEW':assert 'No payment is authorised' in rendered
    else:assert 'trusted record' in rendered and 'replacement contact' in rendered


def test_unknown_decision_cannot_inject_html():
    with pytest.raises(KeyError):decision_banner_html('<script>unexpected</script>')


@pytest.mark.parametrize('mode,configured',[('gemini',False),('offline',True),('gemini',True)])
def test_failed_workbench_retry_removes_old_success(mode,configured):
    tree=ast.parse((ROOT/'app/workbench.py').read_text())
    node=next(n for n in tree.body if isinstance(n,ast.If) and isinstance(n.test,ast.Call)
              and n.test.args and isinstance(n.test.args[0],ast.Constant) and n.test.args[0].value=='◈  Inspect request')
    st=MagicMock();st.session_state=State(inspection=('same','old success'),workflow='NOT_REQUIRED',demo_event='old',verification_outcome='accepted',last_api=99)
    provider=MagicMock(side_effect=RuntimeError('synthetic error'))
    execute(node,dict(st=st,selected_mode=mode,key_configured=lambda:configured,
        time=SimpleNamespace(monotonic=lambda:100),run_case=provider,case={},vendors={},identity='same'))
    assert 'inspection' not in st.session_state and 'workflow' not in st.session_state
    assert 'demo_event' not in st.session_state and 'verification_outcome' not in st.session_state
    rate_limited=mode=='gemini' and configured
    assert st.warning.called==rate_limited
    assert st.error.called==(not rate_limited)
    assert provider.call_count==int(mode=='offline')
    assert st.session_state.last_api==(100 if mode=='offline' else 99)


def test_failed_team_inspection_clears_old_pending_submission():
    tree=ast.parse((ROOT/'app/product.py').read_text())
    node=next(n for n in ast.walk(tree) if isinstance(n,ast.If) and isinstance(n.test,ast.BoolOp)
              and any(isinstance(c,ast.Constant) and c.value=='Inspect request' for c in ast.walk(n.test)))
    st=MagicMock();st.session_state=State(pending_investigation=('same','old'),submission_key='old')
    with pytest.raises(RuntimeError):
        execute(node,dict(st=st,case={'email':{'body':'synthetic'}},mode='offline',
            inspect=MagicMock(side_effect=RuntimeError('synthetic error'))))
    assert not st.session_state


def test_both_apps_share_theme_and_team_defaults_to_offline():
    for name in ('app/product.py','app/workbench.py'):
        source=(ROOT/name).read_text()
        assert 'app/theme.css' in source and 'decision_banner_html' in source
    tree=ast.parse((ROOT/'app/product.py').read_text())
    call=next(n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)
              and n.func.attr=='selectbox' and n.args and isinstance(n.args[0],ast.Constant) and n.args[0].value=='Extractor')
    assert next(k.value.value for k in call.keywords if k.arg=='index')==0
    assert 'radial-gradient' not in (ROOT/'app/workbench.py').read_text()


def test_shared_palette_text_contrast_and_mobile_support():
    css=(ROOT/'app/theme.css').read_text()
    palette=dict(re.findall(r'--tg-([a-z]+):\s*(#[0-9a-fA-F]{6})',css))
    def luminance(hexcolor):
        channels=[int(hexcolor[i:i+2],16)/255 for i in (1,3,5)]
        channels=[c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in channels]
        return sum(a*b for a,b in zip(channels,(.2126,.7152,.0722)))
    for foreground in ('text','muted','clear','review','hold'):
        a,b=sorted((luminance(palette[foreground]),luminance(palette['surface'])))
        assert (b+.05)/(a+.05)>=4.5
    assert '@media(max-width:640px)' in css and ':focus-visible' in css
    assert 'prefers-reduced-motion' in css and '@import' not in css


def test_synthetic_demo_check_passes_without_providers_or_record_mutation():
    spec=importlib.util.spec_from_file_location('demo_check',ROOT/'scripts/demo_check.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    record=ROOT/'data/records/vendor_master.json';before=record.read_bytes()
    report=module.check()
    assert report['passed']==report['total']==15
    assert record.read_bytes()==before
    assert {r['actual'] for r in report['rows']}=={'CLEAR','REVIEW','HOLD','REJECTED'}
