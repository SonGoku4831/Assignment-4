"""Stop only this repository's CPU worker; verify real down alert then recover."""
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1]

def main():
    pid=int((ROOT/'artifacts/backend.pid').read_text().strip())
    args=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
    if args[:2] != [os.fsencode(sys.executable), b'backend.py']:
        raise RuntimeError('Recorded PID does not match the worker started by this project')
    found=[pid]
    evidence={'stopped_pid':found[0],'started':time.time()}
    os.kill(found[0],signal.SIGTERM)
    try:
        deadline=time.monotonic()+65
        while time.monotonic()<deadline:
            alerts=requests.get('http://127.0.0.1:9093/api/v2/alerts',timeout=10).json()
            matched=[a for a in alerts if a['labels'].get('alertname')=='CaptionApplicationDown']
            if matched:
                evidence['received_alerts']=matched; break
            time.sleep(3)
        if 'received_alerts' not in evidence: raise RuntimeError('No downtime alert received in 65 seconds')
    finally:
        env=os.environ.copy(); env['HF_HOME']=str(ROOT/'.cache/huggingface'); env['HF_HUB_DISABLE_XET']='1'
        log=(ROOT/'artifacts/backend.log').open('ab')
        proc=subprocess.Popen([sys.executable,'backend.py'],cwd=ROOT,env=env,stdout=log,stderr=log,start_new_session=True)
        evidence['restarted_pid']=proc.pid
        (ROOT/'artifacts/backend.pid').write_text(str(proc.pid)+'\n')
        for _ in range(30):
            try:
                requests.get('http://127.0.0.1:8001/health',timeout=1).raise_for_status(); break
            except requests.RequestException: time.sleep(1)
        else: raise RuntimeError('Worker failed to restart')
        evidence['finished']=time.time()
        (ROOT/'artifacts/alert-delivery.json').write_text(json.dumps(evidence,indent=2))
    print('Real CaptionApplicationDown reached Alertmanager; worker restarted.')
if __name__=='__main__': main()
