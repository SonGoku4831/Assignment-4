"""DA3408: CPU image captioning with real process-wide metrics."""
import dataclasses
import io
import pandas as pd
import streamlit as st
from captioning import InputError
from client import CaptionClient

st.set_page_config(page_title='Caption Observatory', page_icon='🔭', layout='wide')

@st.cache_resource
def service():
    return CaptionClient()

svc=service()
st.title('Caption Observatory')
st.caption('CPU image captioning · Single images and sequential ZIP batches · Live Prometheus monitoring')
with st.sidebar:
    st.header('Workload settings')
    mode=st.radio('Mode',['Single','Bulk'])
    client=st.selectbox('Client category',['interactive','demonstration'])
    st.caption('Client categories are bounded. IP addresses and session IDs are never exported as labels.')
    st.info('CPU only · 15 MiB/image · 50 MiB/ZIP · 100 images/batch')
    st.caption('Model weights load on first inference. Monitoring uses port 8000.')
if mode=='Single':
    upload=st.file_uploader('Upload one image',type=['png','jpg','jpeg','webp','bmp'])
else:
    upload=st.file_uploader('Upload a ZIP of images',type=['zip'])
run=st.button('Generate captions',type='primary',disabled=upload is None)
if run and upload:
    raw=upload.getvalue()
    with st.status('Processing on CPU…',expanded=True) as status:
        try:
            if mode=='Single':
                result=svc.single(raw,upload.name,client)
                results=[result]
                if not result.error:
                    st.image(io.BytesIO(raw),width=420)
                    st.subheader(result.caption)
            else:
                st.write('The worker processes ZIP images sequentially; results appear when the batch completes.')
                bar=st.progress(0)
                line=st.empty()
                def update(i,n,result):
                    bar.progress(i/n)
                    line.write(f'{i}/{n}: {result.filename} — {result.error or result.caption}')
                results=svc.bulk(raw,client,update)
            errors=sum(bool(r.error) for r in results)
            status.update(label=f'Finished: {len(results)-errors} captions, {errors} failures',state='error' if errors else 'complete')
            st.session_state['results']=[dataclasses.asdict(r) for r in results]
        except (InputError,MemoryError) as e:
            st.error(str(e) if isinstance(e,InputError) else 'Not enough memory. Try a smaller upload.')
            status.update(label='Upload rejected',state='error')
if 'results' in st.session_state:
    frame=pd.DataFrame(st.session_state['results'])
    st.dataframe(frame,hide_index=True,width='stretch')
    st.download_button('Download results CSV',frame.to_csv(index=False),'captions.csv','text/csv')
st.caption('Inference time measures model.generate; per-image processing includes decode and initial model loading. Failures appear in the results table.')
