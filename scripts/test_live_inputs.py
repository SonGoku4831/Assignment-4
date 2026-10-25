"""Real worker failure-path checks; successful member uses the pretrained model."""
import io
import json
import zipfile
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1]
BASE='http://127.0.0.1:8001'
checks=[]
def run(name,path,data,status,verify):
    response=requests.post(BASE+path,data=data,headers={'X-Client-Category':'test'},timeout=120)
    body=response.json()
    passed=response.status_code==status and verify(body)
    checks.append({'name':name,'http_status':response.status_code,'passed':passed,'body':body})
    assert passed,name
run('corrupt image','/single',b'not an image',200,lambda b:bool(b['results'][0]['error']))
run('corrupt ZIP','/bulk',b'not a ZIP',400,lambda b:'error' in b)
f=io.BytesIO()
with zipfile.ZipFile(f,'w'): pass
run('empty ZIP','/bulk',f.getvalue(),400,lambda b:'no supported images' in b.get('error',''))
run('mixed good/corrupt batch','/bulk',(ROOT/'samples/generated/corrupt-image.zip').read_bytes(),200,
    lambda b:len(b['results'])==2 and bool(b['results'][0]['caption']) and not b['results'][0]['error'] and bool(b['results'][1]['error']))
(ROOT/'artifacts/live-input-tests.json').write_text(json.dumps(checks,indent=2))
print(f'{len(checks)} real-worker input checks passed.')
