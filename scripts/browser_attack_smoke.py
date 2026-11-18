"""Synthetic workbench/Attack Lab browser check; no API calls or credentials."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default=str(ROOT/'data/runs/browser-attack'))
    args=parser.parse_args();output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    from playwright.sync_api import sync_playwright
    with tempfile.TemporaryDirectory(prefix='threadgate-attack-ui-') as folder:
        temp=Path(folder)
        wrapper=temp/'wrapper.py'
        wrapper.write_text('import runpy,sys\nfrom datetime import datetime,timezone\n'+
            f'sys.path.insert(0,{str(ROOT/"src")!r})\n'+
            'from threadgate.clock import SystemClock\nSystemClock.now=lambda self:datetime(2026,10,6,tzinfo=timezone.utc)\n'+
            f'runpy.run_path({str(ROOT/"app/workbench.py")!r},run_name="__main__")\n')
        with socket.socket() as sock:sock.bind(('0.0.0.0',0));port=sock.getsockname()[1]
        env=dict(os.environ)
        for key in ['GEMINI_API_KEY','GOOGLE_API_KEY']:env.pop(key,None)
        env.update(THREADGATE_SKIP_DOTENV='1',THREADGATE_DB=str(temp/'demo.sqlite3'))
        with (temp/'server.txt').open('w') as log:
            process=subprocess.Popen([sys.executable,'-m','streamlit','run',str(wrapper),'--server.address','0.0.0.0','--server.port',str(port)],
                cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            try:
                deadline=time.monotonic()+40
                while time.monotonic()<deadline:
                    if process.poll() is not None:raise RuntimeError('Workbench server exited')
                    try:
                        urllib.request.urlopen(f'http://127.0.0.1:{port}/_stcore/health',timeout=1).close();break
                    except OSError:time.sleep(.2)
                else:raise RuntimeError('Workbench startup timed out')
                with sync_playwright() as p:
                    browser=p.chromium.launch(headless=True,args=['--no-sandbox'])
                    context=browser.new_context(viewport={'width':1440,'height':1100})
                    context.route('**/*',lambda r:r.continue_() if r.request.url.startswith(f'http://127.0.0.1:{port}/') else r.abort())
                    page=context.new_page();page.set_default_timeout(20000)
                    page.goto(f'http://127.0.0.1:{port}')
                    page.get_by_text('Attack Lab',exact=True).click()
                    page.get_by_text('Reproducible 16-category attack matrix',exact=True).click()
                    page.get_by_role('button',name='Run synthetic attack matrix',exact=True).click()
                    page.get_by_role('button',name='Download synthetic attack matrix',exact=True).wait_for()
                    with page.expect_download() as downloaded:
                        page.get_by_role('button',name='Download synthetic attack matrix',exact=True).click()
                    path=output/'attack-matrix.json';downloaded.value.save_as(path)
                    report=json.loads(path.read_text());assert report['runs']==48 and report['unsafe_releases']==0
                    page.get_by_text('Reveal sensitive values for this session',exact=True).click()
                    page.get_by_label('Inspect matrix row',exact=True).wait_for()
                    page.screenshot(path=str(output/'06-attack-lab.png'),full_page=True)
                    assert page.get_by_test_id('stException').count()==0
                    browser.close()
                summary={'status':'PASS','scope':'Synthetic Attack Lab matrix UI and JSON download','runs':48,'provider_calls':0,'human_participants':0}
                (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
            finally:
                process.terminate()
                try:process.wait(timeout=10)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
    return 0


if __name__=='__main__':raise SystemExit(main())
