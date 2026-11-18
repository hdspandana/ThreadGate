"""Real-browser, fully synthetic analyst -> verifier -> auditor regression.

No API key required or used. Temporary accounts/database and a test-only wrapper
pin reference time. The shipped product has no test-clock or password bypass.
Requires requirements-browser.txt and Playwright Chromium with OS dependencies.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from threadgate.workspace import Workspace


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default=str(ROOT/'data/runs/browser-smoke'))
    args=parser.parse_args(argv)
    from playwright.sync_api import sync_playwright
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='threadgate-browser-') as folder:
        temp=Path(folder)
        store=Workspace(temp/'workspace.db',require_mfa=False)
        password=secrets.token_urlsafe(32)
        store.bootstrap('browser-owner',password)
        admin=store.login('browser-owner',password)
        for role in ('analyst','verifier','auditor'):
            store.create_user(admin,'browser-'+role,password,role)
        wrapper=temp/'test_app.py'
        wrapper.write_text('import sys,runpy\nfrom datetime import datetime,timezone\n'+
            f'sys.path.insert(0,{str(ROOT / "src")!r})\n'+
            'from threadgate.clock import SystemClock\n'+
            'SystemClock.now=lambda self:datetime(2026,10,6,tzinfo=timezone.utc)\n'+
            f'runpy.run_path({str(ROOT / "app/product.py")!r},run_name="__main__")\n')
        with socket.socket() as sock:
            sock.bind(('0.0.0.0',0));port=sock.getsockname()[1]
        env=dict(os.environ)
        for key in ('GEMINI_API_KEY','GOOGLE_API_KEY'):env.pop(key,None)
        env.update(THREADGATE_SKIP_DOTENV='1',THREADGATE_REQUIRE_MFA='0',THREADGATE_WORKSPACE_DB=str(temp/'workspace.db'))
        with (temp/'server.log').open('w') as log:
            process=subprocess.Popen([sys.executable,'-m','streamlit','run',str(wrapper),
                '--server.address','0.0.0.0','--server.port',str(port),'--browser.gatherUsageStats','false'],
                cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            try:
                deadline=time.monotonic()+40
                while time.monotonic()<deadline:
                    if process.poll() is not None:raise RuntimeError('Test server exited before readiness.')
                    try:
                        with urllib.request.urlopen(f'http://127.0.0.1:{port}/_stcore/health',timeout=1) as response:
                            if response.status==200:break
                    except OSError:time.sleep(.2)
                else:raise RuntimeError('Test server readiness deadline exceeded.')
                with sync_playwright() as playwright:
                    browser=playwright.chromium.launch(headless=True,args=['--no-sandbox'])
                    context=browser.new_context(viewport={'width':1440,'height':1100})
                    context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(f'http://127.0.0.1:{port}/') else route.abort())
                    page=context.new_page();page.set_default_timeout(20000)
                    page.goto(f'http://127.0.0.1:{port}')
                    def login(role):
                        page.get_by_label('Username',exact=True).fill('browser-'+role)
                        page.get_by_label('Password',exact=True).fill(password)
                        # Exercise real tab order and keyboard submission, not
                        # merely CSS/source inspection. No login screenshots.
                        page.get_by_label('Username',exact=True).focus()
                        page.keyboard.press('Tab')
                        assert page.evaluate("document.activeElement.type === 'password'")
                        submit=page.get_by_role('button',name='Sign in',exact=True)
                        submit.focus()
                        assert submit.evaluate("el => getComputedStyle(el).outlineStyle !== 'none' && parseFloat(getComputedStyle(el).outlineWidth) >= 2")
                        page.keyboard.press('Enter')
                        page.get_by_role('button',name='Sign out',exact=True).wait_for()
                    login('analyst')
                    page.get_by_text('New investigation',exact=True).first.click()
                    # Missing-key failure is visible and cannot silently fall
                    # back to the offline engine. Then continue offline.
                    page.get_by_label('Extractor',exact=True).click()
                    page.get_by_role('option',name='gemini',exact=True).click()
                    page.get_by_role('button',name='Inspect request',exact=True).click()
                    page.get_by_text('Configure GEMINI_API_KEY or GOOGLE_API_KEY. No offline fallback is used.',exact=True).wait_for()
                    assert page.get_by_role('button',name='Save investigation to shared inbox',exact=True).count()==0
                    page.get_by_label('Extractor',exact=True).click()
                    page.get_by_role('option',name='offline',exact=True).click()
                    page.get_by_role('button',name='Inspect request',exact=True).click()
                    page.get_by_role('button',name='Save investigation to shared inbox',exact=True).wait_for()
                    assert '50100234559821' not in page.locator('body').inner_text(), 'Destination visible before reveal'
                    assert page.get_by_role('table').count()>=1
                    page.screenshot(path=str(output/'01-investigation.png'),full_page=True)
                    page.get_by_text('Reveal sensitive values for this session',exact=True).click()
                    page.get_by_role('cell',name='50100234559821',exact=True).wait_for()
                    page.screenshot(path=str(output/'03-revealed-comparison.png'),full_page=True)
                    page.get_by_text('Reveal sensitive values for this session',exact=True).click()
                    page.get_by_role('button',name='Save investigation to shared inbox',exact=True).scroll_into_view_if_needed()
                    page.screenshot(path=str(output/'05-evidence-and-next-action.png'),full_page=True)
                    page.get_by_role('button',name='Save investigation to shared inbox',exact=True).click()
                    page.get_by_text('Shared inbox',exact=True).first.click()
                    page.get_by_label('Active verifier username',exact=True).fill('browser-verifier')
                    page.get_by_role('button',name='Assign verifier',exact=True).click()
                    page.get_by_role('button',name='Sign out',exact=True).click()
                    login('verifier')
                    assert page.get_by_text('New investigation',exact=True).count()==0
                    page.get_by_role('button',name='Preview current destination and evidence',exact=True).click()
                    page.get_by_text('I completed out-of-band verification using an independently trusted contact',exact=True).click()
                    page.get_by_text('I verified the exact requested destination and current record version',exact=True).click()
                    page.get_by_role('button',name='Re-inspect and record attestation',exact=True).click()
                    # Inspect the actual persisted transition, not only rendered wording.
                    deadline=time.monotonic()+15
                    while time.monotonic()<deadline:
                        records=store.list_cases(admin)
                        if records and records[0]['state']=='VERIFIED':break
                        page.wait_for_timeout(100)
                    else:raise RuntimeError('Verification did not persist.')
                    page.get_by_role('button',name='Sign out',exact=True).click()
                    login('auditor')
                    assert page.get_by_role('button',name='Assign verifier',exact=True).count()==0
                    assert page.get_by_role('button',name='Re-inspect and record attestation',exact=True).count()==0
                    with page.expect_download() as download:
                        page.get_by_role('button',name='Export verification and audit bundle',exact=True).click()
                    bundle_path=output/'case-bundle.json';download.value.save_as(str(bundle_path))
                    bundle=json.loads(bundle_path.read_text())
                    assert bundle['case']['state']=='VERIFIED'
                    assert bundle['report']['gate_decision']=='HOLD'
                    assert bundle['verification_events'][0]['verifier']=='browser-verifier'
                    assert password not in bundle_path.read_text()
                    page.get_by_text('Workspace audit',exact=True).first.click()
                    page.get_by_role('button',name='Export audit JSON',exact=True).wait_for()
                    page.screenshot(path=str(output/'02-audit.png'),full_page=True)
                    assert page.get_by_test_id('stException').count()==0
                    page.set_viewport_size({'width':390,'height':844})
                    page.screenshot(path=str(output/'04-mobile-audit.png'),full_page=True)
                    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 2')
                    browser.close()
                report={'status':'PASS','scope':'Synthetic real-browser analyst / verifier / auditor flow and JSON download',
                        'api_key_used':False,'keyboard_login_tab_order_and_focus':'PASS','missing_key_no_fallback':'PASS','role_specific_controls':'PASS','mask_default_and_explicit_reveal':'PASS','mobile_390px_no_page_overflow':'PASS','reference_as_of':'2026-10-06','gate_after_verification':'HOLD',
                        'workflow_after_verification':'VERIFIED'}
                (output/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
                print(json.dumps(report,indent=2))
            finally:
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
    return 0


if __name__=='__main__':
    raise SystemExit(main())
