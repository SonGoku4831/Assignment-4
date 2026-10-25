"""AI attribution prompt: Build a professional DA3408 dashboard using caption_*
metrics and node_exporter; include health, mode throughput, errors, mean and
histogram quantiles, bulk size, CPU/RAM/disk and bulk correlation. Explain every
query, use bounded labels, accessible colors, explicit units, linear axes, and 5s refresh.
All generated expressions below use that prompt. See EVALUATION.md for calculations.
"""
import json
import itertools
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DS={'type':'prometheus','uid':'prometheus'}
panels=[]
def panel(title,description,queries,unit='short',kind='timeseries',width=12,height=8, minimum=0):
    i=len(panels)
    used=sum(p['gridPos']['w'] for p in panels)
    # Layout assigned explicitly using rows, preserving aligned panel heights.
    p={'id':i+1,'title':title,'description':description,'type':kind,'datasource':DS,
       'gridPos':{'x':0,'y':0,'w':width,'h':height},
       'fieldConfig':{'defaults':{'unit':unit,'min':minimum,'color':{'mode':'palette-classic'},
        'custom':{'drawStyle':'line','lineInterpolation':'linear','lineWidth':2,'fillOpacity':8,
                  'showPoints':'auto','pointSize':4,'axisLabel':{'short':'Count','s':'Duration (seconds)','bytes':'Memory (bytes)','percent':'Utilization (%)','ops':'Images / second'}.get(unit,unit),'axisCenteredZero':False,
                  'axisColorMode':'text','scaleDistribution':{'type':'linear'},'spanNulls':False}},'overrides':[]},
       'options':{'tooltip':{'mode':'multi','sort':'desc'},'legend':{'displayMode':'table','placement':'bottom','calcs':['lastNotNull','max']}},
       'targets':[{'refId':chr(65+j),'expr':q,'legendFormat':label,'datasource':DS} for j,(q,label) in enumerate(queries)]}
    if kind=='stat': p['options']={'reduceOptions':{'calcs':['lastNotNull'],'fields':'','values':False},'colorMode':'value','graphMode':'area','textMode':'auto'}
    panels.append(p)
    return p
panel('Application availability','1 = metrics endpoint reachable; 0 = scrape failed. This checks scrape health; model readiness is separate.', [('up{job="caption-app"}','Application UP')],kind='stat',width=6,height=4)
panels[-1]['fieldConfig']['defaults']['mappings']=[{'type':'value','options':{'0':{'text':'DOWN','color':'#D55E00'},'1':{'text':'UP','color':'#0072B2'}}}]
panel('Pretrained model ready','1 = CPU model loaded successfully. 0 is expected before first successful load.', [('caption_model_ready','Model ready')],kind='stat',width=6,height=4)
panel('Images attempted','Cumulative per-image attempts, including decode or inference failures. Invalid whole archives are request errors instead.', [('sum(caption_images_total)','Images')],kind='stat',width=6,height=4)
panel('Image outcomes','Cumulative successes and failures, summed over modes and bounded client categories.', [('sum by (outcome) (caption_images_total)','{{outcome}}')],kind='stat',width=6,height=4)
panel('Single versus bulk throughput','Images per second over a rolling 1-minute window. Includes all per-image outcomes.', [('sum by (mode) (rate(caption_images_total[1m]))','{{mode}}')],unit='ops')
panel('Image success and failure counts','Cumulative counts: steps represent actual processed images; restarts reset counters.', [('sum by (mode, outcome) (caption_images_total)','{{mode}} · {{outcome}}')])
panel('Overall image processing rate','Rolling 1-minute rate across modes and results; zero during a stable idle period.', [('sum(rate(caption_images_total[1m]))','Images / second')],unit='ops')
panel('Mean inference latency','Generation seconds divided by completed inference count over 2 minutes. Zero when there are no observations in the window.', [('sum by (mode) (rate(caption_inference_duration_seconds_sum[2m])) / clamp_min(sum by (mode) (rate(caption_inference_duration_seconds_count[2m])), 0.000001)','{{mode}} mean')],unit='s')
panel('Inference latency distribution','P50/P95/P99 estimated from classic histogram buckets over 5 minutes. Quantiles are absent until inference observations exist.', [(f'histogram_quantile({q}, sum by (le) (rate(caption_inference_seconds_bucket[5m])))',label) for q,label in [(.5,'P50'),(.95,'P95'),(.99,'P99')]],unit='s')
panel('Active uploads and CPU inferences','Concurrent uploads include validation and model loading. Model generation is serialized to limit memory.', [('sum by (mode) (caption_active_requests)','{{mode}} uploads'),('caption_active_inferences','CPU inference')])
panel('Bulk workload and batch size','Active bulk is transient. Last batch size persists after completion so idle periods remain interpretable.', [('caption_bulk_active','Active bulk uploads'),('caption_last_batch_size','Last batch images')])
panel('Upload duration','Mean whole request seconds over 5 minutes, including decode and model cold start.', [('sum by (mode) (rate(caption_request_duration_seconds_sum[5m])) / clamp_min(sum by (mode) (rate(caption_request_duration_seconds_count[5m])), 0.000001)','{{mode}} mean')],unit='s')
panel('Host CPU utilization','100 × (1 − average idle CPU rate). Scope is the available cloud host, which can include other activity.', [('100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle",job="node"}[1m])))','Host CPU')],unit='percent')
panel('Host RAM utilization','100 × (1 − available RAM / total RAM). Available includes reclaimable cache.', [('100 * (1 - node_memory_MemAvailable_bytes{job="node"}/node_memory_MemTotal_bytes{job="node"})','Host RAM')],unit='percent')
panel('Caption process RSS','Resident process bytes sampled every second; includes Python, tensors and loaded weights.', [('caption_process_memory_bytes','Caption process RSS')],unit='bytes')
panel('Disk utilization','Percentage used on writable real filesystems. In containers the root overlay may represent the cloud machine filesystem.', [('100 * (1 - node_filesystem_avail_bytes{job="node",fstype!~"tmpfs|devtmpfs|squashfs|proc|sysfs"} / node_filesystem_size_bytes{job="node",fstype!~"tmpfs|devtmpfs|squashfs|proc|sysfs"})','{{mountpoint}} · {{device}}')],unit='percent')
p=panel('Bulk correlation · CPU and activity','Shared time axis: compare CPU percent against the right-axis bulk-active signal. Correlation does not establish causation.', [('100 * (1 - avg(rate(node_cpu_seconds_total{mode="idle",job="node"}[30s])))','CPU %'),('caption_bulk_active','Bulk active')],unit='percent')
p['fieldConfig']['overrides'].append({'matcher':{'id':'byName','options':'Bulk active'},'properties':[{'id':'unit','value':'short'},{'id':'custom.axisPlacement','value':'right'},{'id':'custom.axisLabel','value':'Active bulk uploads (count)'},{'id':'custom.drawStyle','value':'bars'}]})
p=panel('Bulk correlation · memory and activity','Process RSS with the bulk-active signal on a separate right axis. Model loading also changes memory.', [('caption_process_memory_bytes','Process RSS'),('caption_bulk_active','Bulk active')],unit='bytes')
p['fieldConfig']['overrides'].append({'matcher':{'id':'byName','options':'Bulk active'},'properties':[{'id':'unit','value':'short'},{'id':'custom.axisPlacement','value':'right'},{'id':'custom.axisLabel','value':'Active bulk uploads (count)'},{'id':'custom.drawStyle','value':'bars'}]})
panel('Errors by operation','Cumulative errors distinguish archive validation, image decode, model loading, and inference.', [('sum by (mode,operation) (caption_errors_total)','{{mode}} · {{operation}}')])
panel('Batch size distribution','Histogram-derived mean number of candidate images in bulk uploads over 5 minutes.', [('rate(caption_batch_images_sum[5m]) / clamp_min(rate(caption_batch_images_count[5m]), 0.000001)','Mean batch images')])
# Colorblind-safe Okabe-Ito palette; legends and line styles add redundant identity.
colors=['#0072B2','#E69F00','#009E73','#CC79A7','#56B4E9','#D55E00']
x=y=rowh=0
for p in panels:
    w,h=p['gridPos']['w'],p['gridPos']['h']
    if x+w>24: x=0; y+=rowh; rowh=0
    p['gridPos'].update(x=x,y=y); x+=w; rowh=max(rowh,h)
    for j,target in enumerate(p['targets']):
        p['fieldConfig']['overrides'].append({'matcher':{'id':'byFrameRefID','options':target['refId']},'properties':[{'id':'color','value':{'mode':'fixed','fixedColor':colors[j%len(colors)]}},{'id':'custom.lineStyle','value':{'fill':'solid' if j==0 else 'dash'}}]})
    if p['type']=='timeseries' and any('{{' in q['legendFormat'] for q in p['targets']):
        # Dynamic series retain separate palette colors; each also has a text legend.
        p['fieldConfig']['overrides']=[o for o in p['fieldConfig']['overrides'] if o['matcher']['id']!='byFrameRefID']
        p['fieldConfig']['defaults']['color']={'mode':'palette-classic'}
# Assign the same accessible palette to bounded dynamically named series.
for p in panels:
    for target in p['targets']:
        template=target['legendFormat']
        keys=[k for k in ['mode','outcome','operation'] if '{{'+k+'}}' in template]
        if not keys: continue
        domains={'mode':['single','bulk'],'outcome':['success','error'],'operation':['validation','decode','inference','model']}
        for j,values in enumerate(itertools.product(*(domains[k] for k in keys))):
            name=template
            for key,value in zip(keys,values): name=name.replace('{{'+key+'}}',value)
            p['fieldConfig']['overrides'].append({'matcher':{'id':'byName','options':name},'properties':[
                {'id':'color','value':{'mode':'fixed','fixedColor':colors[j%len(colors)]}},
                {'id':'custom.lineStyle','value':{'fill':'solid' if j%2==0 else 'dash'}}]})
dashboard={'id':None,'uid':'caption-observatory','title':'Caption Observatory · CPU Image Captioning',
 'description':'DA3408 · Health → workload → latency → hardware. Real 5-second scrapes. AI-generated PromQL: attribution prompt and worked calculations are in EVALUATION.md and scripts/build_dashboard.py.',
 'tags':['DA3408','CPU','observability'],'schemaVersion':41,'version':1,'timezone':'browser',
 'refresh':'5s','time':{'from':'now-15m','to':'now'},'panels':panels,'annotations':{'list':[]},
 'templating':{'list':[]},'editable':True}
dashboard['description'] += '\nAI prompt: Build a professional DA3408 dashboard using caption_* metrics and node_exporter; include health, mode throughput, errors, mean and histogram quantiles, bulk size, CPU/RAM/disk and bulk correlation. Explain every query, use bounded labels, accessible colors, explicit units, linear axes, and 5s refresh. Include overlay filesystems for a container-based cloud machine while excluding pseudo filesystems.'
path=ROOT/'monitoring/grafana/dashboards/caption-observatory.json'
path.write_text(json.dumps(dashboard,indent=2)+'\n')
print(f'Wrote {len(panels)} panels to {path}')
if __name__=='__main__': pass
