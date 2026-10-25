"""Real browser uploads and optional 65-second Grafana recording; no fake inference."""
import argparse
import os
import shutil
import playwright
import json
import time
import threading
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from client import CaptionClient
# Reuse the system FFmpeg rather than download a redundant browser encoder.
# Playwright's registry discovers the binary in its configured local cache.
registry=json.loads((Path(playwright.__file__).parent/'driver/package/browsers.json').read_text())
revision=next(x['revision'] for x in registry['browsers'] if x['name']=='ffmpeg')
encoder=shutil.which('ffmpeg')
if encoder:
    cache=ROOT/'.cache/playwright'
    os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(cache))
    target=Path(os.environ['PLAYWRIGHT_BROWSERS_PATH'])/f'ffmpeg-{revision}'/'ffmpeg-linux'
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists(): target.symlink_to(encoder)

grafana_user=os.getenv('GRAFANA_USER','admin')
grafana_password=os.getenv('GRAFANA_PASSWORD','admin')
p=argparse.ArgumentParser(); p.add_argument('--record',action='store_true'); p.add_argument('--bulk',action='store_true'); args=p.parse_args()
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    options={'viewport':{'width':1600,'height':1000},'http_credentials':{'username':grafana_user,'password':grafana_password}}
    if args.record:
        options['record_video_dir']=str(ROOT/'artifacts/video')
        options['record_video_size']={'width':1600,'height':1000}
    context=browser.new_context(**options)
    page=context.new_page()
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://127.0.0.1:8501',wait_until='networkidle')
    page.get_by_role('heading',name='Caption Observatory',exact=True).wait_for(timeout=60000)
    page.screenshot(path=str(ROOT/'artifacts/streamlit-idle.png'),full_page=True)
    # Real browser file upload drives the same callback as a user.
    page.locator('input[type=file]').set_input_files(str(ROOT/'samples/generated/flower.jpg'))
    page.get_by_role('button',name='Generate captions',exact=True).click()
    page.get_by_text('Finished:',exact=False).wait_for(timeout=240000)
    page.wait_for_timeout(1500)
    page.screenshot(path=str(ROOT/'artifacts/streamlit-single.png'),full_page=True)
    single=page.locator('body').inner_text()
    if args.bulk:
        page.get_by_text('Bulk',exact=True).click()
        page.get_by_text('Upload a ZIP of images',exact=True).wait_for(timeout=30000)
        page.wait_for_timeout(1000)
        page.locator('input[type=file]').set_input_files(str(ROOT/'samples/generated/bulk-10.zip'))
        page.get_by_role('button',name='Generate captions',exact=True).click()
        page.get_by_text('Finished: 10 captions, 0 failures',exact=False).wait_for(timeout=360000)
        page.screenshot(path=str(ROOT/'artifacts/streamlit-bulk.png'),full_page=True)
    bulk=page.locator('body').inner_text() if args.bulk else ''
    graf=context.new_page()
    graf.on('pageerror',lambda error:errors.append(str(error)))
    graf.goto('http://127.0.0.1:3000/d/caption-observatory?orgId=1&from=now-15m&to=now&refresh=5s',wait_until='networkidle')
    if '/login' in graf.url:
        graf.get_by_label('Email or username').fill(grafana_user)
        graf.get_by_label('Password',exact=True).fill(grafana_password)
        graf.get_by_role('button',name='Log in',exact=True).click()
        graf.wait_for_timeout(2000)
    skip=graf.get_by_role('button',name='Skip',exact=True)
    if skip.count(): skip.click()
    graf.get_by_text('Application availability',exact=True).wait_for(timeout=60000)
    graf.wait_for_timeout(12000)
    graf.screenshot(path=str(ROOT/'artifacts/grafana-dashboard.png'),full_page=False)
    tour_started=time.time()
    live_workload={}
    live_thread=None
    if args.record:
        def run_live():
            time.sleep(10)
            live_workload['started']=time.time()
            try:
                client=CaptionClient()
                single_live=client.single((ROOT/'samples/generated/flower.jpg').read_bytes(),'flower.jpg','demonstration')
                bulk_live=client.bulk((ROOT/'samples/generated/bulk-10.zip').read_bytes(),'demonstration')
                live_workload['results']=[vars(r) for r in [single_live]+bulk_live]
            except Exception as e: live_workload['error']=str(e)
            live_workload['finished']=time.time()
        live_thread=threading.Thread(target=run_live,daemon=True)
        live_thread.start()
    if args.record:
        # Actual Grafana page at 5-second refresh; no fabricated overlays or data.
        for section in range(13):
            graf.mouse.move(1300,700)
            graf.mouse.wheel(0,700 if section%5<4 else -4000)
            graf.wait_for_timeout(5000)
    if live_thread: live_thread.join(timeout=30)
    (ROOT/'artifacts/browser-verification.json').write_text(json.dumps({'single_page_text':single,'browser_errors':errors,'grafana_url':graf.url,'recorded':args.record,'single_success': 'Finished: 1 captions, 0 failures' in single,'bulk_success': 'Finished: 10 captions, 0 failures' in bulk,'bulk_page_text':bulk,'tour_started':tour_started,'finished':time.time(),'grafana_video':str(graf.video.path()) if args.record else None,'live_workload':live_workload},indent=2))
    context.close(); browser.close()
    if 'Finished: 1 captions, 0 failures' not in single: sys.exit('Single browser inference failed')
    if args.bulk and 'Finished: 10 captions, 0 failures' not in bulk: sys.exit('Bulk browser inference failed')
