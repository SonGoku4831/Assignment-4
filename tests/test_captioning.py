import io
import zipfile
import pytest
from PIL import Image
from prometheus_client import generate_latest
from captioning import CaptionService, Metrics, InputError, decode_image, zip_members

def image():
    f=io.BytesIO(); Image.new('RGB',(32,32),'blue').save(f,format='PNG'); return f.getvalue()

def archive(items):
    f=io.BytesIO()
    with zipfile.ZipFile(f,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in items: z.writestr(name,data)
    return f.getvalue()

@pytest.fixture
def service():
    # Explicit stub for unit tests only. Real-model integration never uses this.
    return CaptionService(Metrics(),model_factory=lambda: lambda im:'unit-test caption')

def value(s,name,labels={}):
    return s.metrics.registry.get_sample_value(name,labels)

def test_single_metrics(service):
    r=service.single(image(),client='test')
    assert r.caption=='unit-test caption' and not r.error
    assert value(service,'caption_images_total',{'mode':'single','outcome':'success','client':'test'})==1
    assert value(service,'caption_inference_seconds_count',{'mode':'single'})==1
    assert value(service,'caption_inference_duration_seconds_count',{'mode':'single'})==1
    assert value(service,'caption_active_requests',{'mode':'single'})==0
    assert value(service,'caption_active_inferences')==0

def test_bulk_continues_after_corruption(service):
    r=service.bulk(archive([('good.png',image()),('bad.jpg',b'corrupt'),('last.png',image())]),client='test')
    assert len(r)==3 and sum(bool(x.error) for x in r)==1
    assert value(service,'caption_bulk_active')==0
    assert value(service,'caption_last_batch_size')==3
    assert value(service,'caption_images_total',{'mode':'bulk','outcome':'success','client':'test'})==2
    assert value(service,'caption_images_total',{'mode':'bulk','outcome':'error','client':'test'})==1

@pytest.mark.parametrize('items',[[],[('readme.txt',b'x')],[('../evil.png',b'x')],[('/absolute.png',b'x')],[(f'{i}.png',b'x') for i in range(101)]])
def test_archive_rejections(service,items):
    with pytest.raises(InputError): service.bulk(archive(items),client='test')
    assert value(service,'caption_bulk_active')==0
    assert value(service,'caption_active_requests',{'mode':'bulk'})==0
    assert value(service,'caption_errors_total',{'mode':'bulk','operation':'validation','client':'test'})==1

def test_corrupt_zip(service):
    with pytest.raises(InputError): service.bulk(b'invalid',client='test')

def test_bad_image(service):
    r=service.single(b'invalid',client='test')
    assert r.error
    assert value(service,'caption_errors_total',{'mode':'single','operation':'decode','client':'test'})==1

def test_memory_failure_cleanup():
    def fail(im): raise MemoryError('test')
    s=CaptionService(Metrics(),model_factory=lambda:fail)
    assert 'memory' in s.single(image(),client='test').error
    assert value(s,'caption_active_inferences')==0
    assert value(s,'caption_active_requests',{'mode':'single'})==0

def test_model_failure_is_not_ready():
    def fail(): raise RuntimeError('model unavailable')
    s=CaptionService(Metrics(),model_factory=fail)
    assert s.single(image(),client='test').error
    assert value(s,'caption_model_ready')==0

def test_labels_bounded(service):
    with pytest.raises(ValueError): service.single(image(),client='arbitrary-session-id')

def test_dimensions_rejected(monkeypatch):
    monkeypatch.setattr(Image,'MAX_IMAGE_PIXELS',100)
    with pytest.raises(InputError): decode_image(image())

def test_byte_limit_rejected(monkeypatch):
    import captioning
    monkeypatch.setattr(captioning,'MAX_IMAGE_BYTES',1)
    with pytest.raises(InputError): decode_image(image())

def test_metrics_exposition(service):
    service.single(image(),client='test')
    text=generate_latest(service.metrics.registry).decode()
    for metric in ['caption_images_total','caption_inference_seconds_bucket','caption_inference_duration_seconds_sum','caption_inference_duration_seconds_count','caption_process_memory_bytes']:
        assert metric in text
