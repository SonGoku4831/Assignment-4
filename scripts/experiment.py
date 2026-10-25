"""Measured baseline → single → bulk → recovery via the same worker used by UI."""
import argparse
import json
import sys
import threading
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import requests
from client import CaptionClient
from check_stack import snapshot
ROOT=Path(__file__).resolve().parents[1]

def metrics():
    r=requests.get('http://127.0.0.1:8000/metrics',timeout=10); r.raise_for_status(); return r.text

def main():
    p=argparse.ArgumentParser(); p.add_argument('--idle-seconds',type=int,default=30); args=p.parse_args()
    out={'started':time.time(),'samples':[],'phases':{}}
    stop=threading.Event(); phase=['idle']
    def sample():
        while not stop.is_set():
            try: out['samples'].append({'phase':phase[0],**snapshot()})
            except Exception as e: out['samples'].append({'phase':phase[0],'error':str(e)})
            stop.wait(2)
    thread=threading.Thread(target=sample,daemon=True); thread.start()
    client=CaptionClient()
    try:
        time.sleep(args.idle_seconds)
        (ROOT/'artifacts/metrics-before.txt').write_text(metrics())
        out['phases']['idle']=snapshot()
        phase[0]='single'
        start=time.time()
        single=client.single((ROOT/'samples/generated/flower.jpg').read_bytes(),'flower.jpg','demonstration')
        out['phases']['single']={'started':start,'finished':time.time(),'results':[vars(single)]}
        (ROOT/'artifacts/metrics-after-single.txt').write_text(metrics())
        phase[0]='bulk'
        start=time.time()
        bulk=client.bulk((ROOT/'samples/generated/bulk-10.zip').read_bytes(),'demonstration')
        out['phases']['bulk']={'started':start,'finished':time.time(),'results':[vars(r) for r in bulk]}
        (ROOT/'artifacts/metrics-after-bulk.txt').write_text(metrics())
        phase[0]='recovery'
        time.sleep(15)
        out['phases']['recovery']=snapshot()
        out['caption_successes']=sum(not r.error for r in [single]+bulk)
        out['caption_failures']=sum(bool(r.error) for r in [single]+bulk)
    finally:
        stop.set(); thread.join(timeout=5)
        out['finished']=time.time()
        (ROOT/'artifacts/experiment.json').write_text(json.dumps(out,indent=2))
    print(json.dumps({'successes':out.get('caption_successes'),'failures':out.get('caption_failures'),'report':'artifacts/experiment.json'}))
    if out.get('caption_successes')!=11: sys.exit(1)
if __name__=='__main__': main()
