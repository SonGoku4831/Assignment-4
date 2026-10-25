"""Verify real services and all dashboard queries. Non-finite/missing data is explicit."""
import json
import os
import time
from pathlib import Path
import requests
ROOT=Path(__file__).resolve().parents[1]

def query(expr):
    response=requests.get('http://127.0.0.1:9090/api/v1/query',params={'query':expr},timeout=20)
    response.raise_for_status()
    body=response.json()
    if body['status']!='success': raise RuntimeError(body)
    return body['data']['result']

def snapshot():
    return {'timestamp':time.time(),'metrics':{q:query(q) for q in [
        'up','caption_model_ready','sum by (mode,outcome) (caption_images_total)',
        'sum by (mode,operation) (caption_errors_total)','sum(caption_active_requests)',
        'caption_active_inferences','caption_bulk_active','caption_last_batch_size',
        'caption_process_memory_bytes','100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[30s])))',
        '100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)',
        'sum by (mode) (caption_inference_duration_seconds_count)',
        'sum by (mode) (caption_inference_duration_seconds_sum)']}}

def main():
    auth=(os.getenv('GRAFANA_USER','admin'),os.getenv('GRAFANA_PASSWORD','admin'))
    session=requests.Session(); session.auth=auth
    health=session.get('http://127.0.0.1:3000/api/datasources/uid/prometheus/health',timeout=15)
    health.raise_for_status()
    dashboard=json.loads((ROOT/'monitoring/grafana/dashboards/caption-observatory.json').read_text())
    imported=session.get('http://127.0.0.1:3000/api/dashboards/uid/caption-observatory',timeout=15)
    imported.raise_for_status()
    (ROOT/'artifacts/grafana-export.json').write_text(json.dumps(imported.json()['dashboard'],indent=2))
    checks=[]
    for panel in dashboard['panels']:
        for target in panel['targets']:
            result=query(target['expr'])
            finite=any(x.get('value',[None,'NaN'])[1] not in ('NaN','+Inf','-Inf') for x in result)
            checks.append({'panel':panel['title'],'query':target['expr'],'series':len(result),'has_finite_data':finite,'result':result})
    output={'snapshot':snapshot(),'datasource':health.json(),'dashboard_imported':True,'panels':len(dashboard['panels']),'queries':checks}
    (ROOT/'artifacts/stack-verification.json').write_text(json.dumps(output,indent=2))
    print(json.dumps({'panels':output['panels'],'queries':len(checks),'with_finite_data':sum(x['has_finite_data'] for x in checks),'without_finite_data':[x['panel'] for x in checks if not x['has_finite_data']],'datasource':health.json()}))
if __name__=='__main__': main()
