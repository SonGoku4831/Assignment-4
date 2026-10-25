"""Assert counter deltas and summarize actual sampled resources; no invented spikes."""
import json
import statistics
from pathlib import Path
from prometheus_client.parser import text_string_to_metric_families
ROOT=Path(__file__).resolve().parents[1]

def samples(filename):
    return [s for f in text_string_to_metric_families((ROOT/'artifacts'/filename).read_text()) for s in f.samples]
def total(rows,name,**labels):
    return sum(s.value for s in rows if s.name==name and all(s.labels.get(k)==v for k,v in labels.items()))
def main():
    before,single,bulk=[samples(f) for f in ['metrics-before.txt','metrics-after-single.txt','metrics-after-bulk.txt']]
    exp=json.loads((ROOT/'artifacts/experiment.json').read_text())
    assert total(single,'caption_images_total',mode='single',outcome='success')-total(before,'caption_images_total',mode='single',outcome='success')==1
    assert total(bulk,'caption_images_total',mode='bulk',outcome='success')-total(single,'caption_images_total',mode='bulk',outcome='success')==10
    assert total(bulk,'caption_images_total',outcome='error')-total(before,'caption_images_total',outcome='error')==0
    assert total(bulk,'caption_inference_seconds_count')-total(before,'caption_inference_seconds_count')==11
    assert total(bulk,'caption_inference_duration_seconds_count')-total(before,'caption_inference_duration_seconds_count')==11
    assert total(bulk,'caption_inference_duration_seconds_sum')>total(before,'caption_inference_duration_seconds_sum')
    assert total(bulk,'caption_active_requests')==0
    assert total(bulk,'caption_active_inferences')==0
    assert total(bulk,'caption_bulk_active')==0
    assert total(bulk,'caption_last_batch_size')==10
    summary={'assertions':'PASS','successes':exp['caption_successes'],'failures':exp['caption_failures'],'phases':{},'inference_seconds_mean':{},'cold_start_single_wall_seconds':exp['phases']['single']['finished']-exp['phases']['single']['started'],'bulk_wall_seconds':exp['phases']['bulk']['finished']-exp['phases']['bulk']['started']}
    for mode in ['single','bulk']:
        count=total(bulk,'caption_inference_duration_seconds_count',mode=mode)-total(before,'caption_inference_duration_seconds_count',mode=mode)
        duration=total(bulk,'caption_inference_duration_seconds_sum',mode=mode)-total(before,'caption_inference_duration_seconds_sum',mode=mode)
        summary['inference_seconds_mean'][mode]=duration/count if count else None
    for phase in ['idle','single','bulk','recovery']:
        rows=[s for s in exp['samples'] if s['phase']==phase and 'metrics' in s]
        stats={}
        for query in ['100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle"}[30s])))','100 * (1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)','caption_process_memory_bytes','caption_bulk_active','caption_active_inferences']:
            values=[float(r['metrics'][query][0]['value'][1]) for r in rows if r['metrics'].get(query)]
            if values: stats[query]={'min':min(values),'mean':statistics.mean(values),'max':max(values),'samples':len(values)}
        summary['phases'][phase]=stats
    (ROOT/'artifacts/experiment-summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
if __name__=='__main__': main()
