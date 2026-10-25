"""Record a genuine 65-second Grafana tour with a live CPU workload and export 60s MP4."""
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path
import playwright
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from client import CaptionClient
registry=json.loads((Path(playwright.__file__).parent/'driver/package/browsers.json').read_text())
revision=next(x['revision'] for x in registry['browsers'] if x['name']=='ffmpeg')
os.environ.setdefault('PLAYWRIGHT_BROWSERS_PATH',str(ROOT/'.cache/playwright'))
encoder=Path(os.environ['PLAYWRIGHT_BROWSERS_PATH'])/f'ffmpeg-{revision}/ffmpeg-linux'
encoder.parent.mkdir(parents=True,exist_ok=True)
if not encoder.exists(): encoder.symlink_to(shutil.which('ffmpeg'))
user=os.getenv('GRAFANA_USER','admin'); password=os.getenv('GRAFANA_PASSWORD','admin')
workload={}
def load():
    time.sleep(10)
    workload['started']=time.time()
    try:
        client=CaptionClient()
        single=client.single((ROOT/'samples/generated/flower.jpg').read_bytes(),'flower.jpg','demonstration')
        bulk=client.bulk((ROOT/'samples/generated/bulk-10.zip').read_bytes(),'demonstration')
        workload['results']=[vars(r) for r in [single]+bulk]
    except Exception as e: workload['error']=str(e)
    workload['finished']=time.time()
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox','--disable-dev-shm-usage'])
    context=browser.new_context(viewport={'width':1600,'height':1000},record_video_size={'width':1600,'height':1000},record_video_dir=str(ROOT/'artifacts/video'))
    page=context.new_page(); page_created=time.time()
    errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto('http://127.0.0.1:3000/d/caption-observatory?orgId=1&from=now-5m&to=now&refresh=5s',wait_until='networkidle')
    if '/login' in page.url:
        page.get_by_label('Email or username').fill(user)
        page.get_by_label('Password',exact=True).fill(password)
        page.get_by_role('button',name='Log in',exact=True).click()
        page.wait_for_timeout(1500)
    if page.get_by_role('button',name='Skip',exact=True).count(): page.get_by_role('button',name='Skip',exact=True).click()
    page.get_by_text('Application availability',exact=True).wait_for(timeout=60000)
    page.wait_for_timeout(15000)
    # Save a rendered overview, not the empty loading layout.
    page.screenshot(path=str(ROOT/'artifacts/grafana-dashboard.png'))
    started=time.time()
    thread=threading.Thread(target=load,daemon=True); thread.start()
    for i in range(13):
        page.mouse.move(1300,700)
        # First 10 seconds show overview; then reveal latency and hardware panels.
        if i in (2,4,6,8): page.mouse.wheel(0,650)
        if i==10: page.mouse.wheel(0,-4000)
        page.wait_for_timeout(5000)
        if i in (4,8): page.screenshot(path=str(ROOT/f'artifacts/grafana-section-{i}.png'))
    finished=time.time(); thread.join(timeout=30)
    video=str(page.video.path())
    context.close(); browser.close()
meta={'source':video,'page_created':page_created,'tour_started':started,'finished':finished,'workload':workload,'browser_errors':errors,'refresh':'5s'}
duration=float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',video],text=True).strip())
offset=max(0,duration-(finished-started)-.5)
out=ROOT/'artifacts/dashboard-demo.mp4'
subprocess.run(['ffmpeg','-y','-hide_banner','-loglevel','error','-ss',str(offset),'-i',video,'-t','60','-c:v','libx264','-preset','fast','-crf','23','-pix_fmt','yuv420p',str(out)],check=True)
meta.update(source_duration=duration,trim_offset=offset,output=str(out))
(ROOT/'artifacts/video-verification.json').write_text(json.dumps(meta,indent=2))
assert len(workload.get('results',[]))==11 and not any(r['error'] for r in workload['results'])
assert not errors,errors
print('Recorded real live workload and saved 60-second dashboard-demo.mp4')
