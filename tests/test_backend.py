import threading
import requests
import pytest
from backend import WorkerServer
from captioning import CaptionService, Metrics
from test_captioning import image, archive

@pytest.fixture
def worker():
    service=CaptionService(Metrics(),model_factory=lambda:lambda im:'unit-test caption')
    server=WorkerServer(('127.0.0.1',0),service)
    thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    yield f'http://127.0.0.1:{server.server_port}',service
    server.shutdown(); server.server_close(); thread.join()

def test_health(worker):
    base,s=worker
    body=requests.get(base+'/health').json()
    assert body=={'status':'ok','device':'cpu','model_ready':False}

def test_http_single_and_bulk(worker):
    base,s=worker
    r=requests.post(base+'/single',data=image(),headers={'X-Client-Category':'test'})
    assert r.status_code==200 and r.json()['results'][0]['caption']=='unit-test caption'
    r=requests.post(base+'/bulk',data=archive([(f'{i}.png',image()) for i in range(10)]))
    assert r.status_code==200 and len(r.json()['results'])==10
    assert all(not x['error'] for x in r.json()['results'])

def test_http_validation(worker):
    base,s=worker
    assert requests.post(base+'/single',data=b'').status_code==413
    assert requests.post(base+'/bulk',data=b'invalid').status_code==400
    assert requests.post(base+'/single',data=image(),headers={'X-Client-Category':'unbounded'}).status_code==400
    assert requests.post(base+'/not-real',data=image()).status_code==404

def test_http_busy(worker):
    base,s=worker
    # This fixture exposes two slots; exhaust both to test overload handling.
    # Access through a dedicated server instance for deterministic ownership.
    server=WorkerServer(('127.0.0.1',0),s)
    server.slots.acquire(); server.slots.acquire()
    t=threading.Thread(target=server.serve_forever,daemon=True); t.start()
    try:
        assert requests.post(f'http://127.0.0.1:{server.server_port}/single',data=image()).status_code==429
    finally:
        server.shutdown(); server.server_close(); t.join()
