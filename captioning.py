"""CPU-only captioning, bounded uploads, and process-wide Prometheus instrumentation."""
from __future__ import annotations
import io
import os
import threading
import time
import warnings
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Callable

import psutil
from PIL import Image, ImageOps, UnidentifiedImageError
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, Summary, start_http_server

MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_BATCH = 100
MAX_EXPANDED_BYTES = 150 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 20_000_000
MODES = ('single', 'bulk')
CLIENTS = ('interactive', 'demonstration', 'test')

class InputError(ValueError):
    pass

class Metrics:
    def __init__(self, registry=None):
        self.registry = registry or CollectorRegistry()
        r = self.registry
        self.images = Counter('caption_images', 'Attempted images by result.', ['mode', 'outcome', 'client'], registry=r)
        self.errors = Counter('caption_errors', 'Failures by bounded operation.', ['mode', 'operation', 'client'], registry=r)
        self.requests = Counter('caption_requests', 'Completed upload requests.', ['mode', 'outcome', 'client'], registry=r)
        self.active = Gauge('caption_active_requests', 'Uploads being processed.', ['mode'], registry=r)
        self.inflight = Gauge('caption_active_inferences', 'CPU inferences in progress.', registry=r)
        self.bulk = Gauge('caption_bulk_active', 'Bulk requests in progress.', registry=r)
        self.batch = Gauge('caption_last_batch_size', 'Number of candidate images in the last bulk request.', registry=r)
        self.memory = Gauge('caption_process_memory_bytes', 'Caption process RSS.', registry=r)
        self.model_ready = Gauge('caption_model_ready', 'Whether pretrained CPU model is loaded.', registry=r)
        self.inference = Histogram('caption_inference_seconds', 'Model generation latency.', ['mode'], buckets=(.1,.25,.5,1,2,4,8,16,32,64,128), registry=r)
        self.processing = Histogram('caption_processing_seconds', 'Decode plus generation time per image.', ['mode'], buckets=(.1,.5,1,2,4,8,16,32,64,128), registry=r)
        self.summary = Summary('caption_inference_duration_seconds', 'Generation duration sum and count.', ['mode'], registry=r)
        self.upload_duration = Summary('caption_request_duration_seconds', 'Whole upload duration sum and count.', ['mode'], registry=r)
        self.batch_sizes = Histogram('caption_batch_images', 'Candidate images per bulk upload.', buckets=(1,5,10,20,50,100), registry=r)
        self.started = Gauge('caption_started_timestamp_seconds', 'Metrics service start time.', registry=r)
        self.started.set(time.time())
        for mode in MODES:
            self.active.labels(mode).set(0)
            self.inference.labels(mode)
            self.processing.labels(mode)
            self.summary.labels(mode)
            self.upload_duration.labels(mode)
            for client in CLIENTS:
                for outcome in ('success','error'):
                    self.images.labels(mode,outcome,client)
                    self.requests.labels(mode,outcome,client)
                for op in ('validation','decode','inference','model'):
                    self.errors.labels(mode,op,client)
        self.update_memory()

    def update_memory(self):
        self.memory.set(psutil.Process().memory_info().rss)

    def serve(self, port=8000):
        # Bind to all interfaces only when explicitly configured (e.g. Docker).
        self.server, self.thread = start_http_server(port, addr=os.getenv('METRICS_HOST','127.0.0.1'), registry=self.registry)
        def sample():
            while self.thread.is_alive():
                self.update_memory()
                time.sleep(1)
        threading.Thread(target=sample, daemon=True, name='caption-rss').start()


def decode_image(data: bytes) -> Image.Image:
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise InputError('Image must contain 1 byte to 15 MiB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as check:
                check.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
                rgb = ImageOps.exif_transpose(image).convert('RGB')
                rgb.thumbnail((2048,2048))
                return rgb.copy()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning) as e:
        raise InputError('Invalid, corrupt, or excessively large image.') from e


def zip_members(data: bytes):
    """Validate all archive metadata before reading; never extract to the filesystem."""
    if not data or len(data) > MAX_ZIP_BYTES:
        raise InputError('ZIP must contain 1 byte to 50 MiB.')
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        entries = archive.infolist()
        if len(entries) > 1000:
            raise InputError('Archive contains too many entries.')
        candidates=[]
        expanded=0
        for item in entries:
            path=PurePosixPath(item.filename.replace('\\','/'))
            if item.is_dir():
                continue
            if path.is_absolute() or '..' in path.parts:
                raise InputError('Unsafe archive member path.')
            expanded += item.file_size
            if expanded > MAX_EXPANDED_BYTES:
                raise InputError('ZIP expanded size exceeds 150 MiB.')
            if item.flag_bits & 1:
                raise InputError('Encrypted ZIP entries are not supported.')
            if path.suffix.lower() in ('.png','.jpg','.jpeg','.webp','.bmp'):
                if item.file_size > MAX_IMAGE_BYTES:
                    raise InputError('An image exceeds 15 MiB.')
                candidates.append(item)
        if not candidates:
            raise InputError('ZIP contains no supported images.')
        if len(candidates) > MAX_BATCH:
            raise InputError('Maximum batch size is 100 images.')
        return archive, candidates
    except (zipfile.BadZipFile, zipfile.LargeZipFile) as e:
        raise InputError('Invalid or corrupt ZIP.') from e

class CaptionModel:
    def __init__(self):
        import torch
        from transformers import BlipProcessor, BlipForConditionalGeneration
        torch.set_num_threads(max(1,min(int(os.getenv('CPU_THREADS','2')),4)))
        self.torch = torch
        model = os.getenv('CAPTION_MODEL','Salesforce/blip-image-captioning-base')
        revision = None if os.path.isdir(model) else os.getenv('CAPTION_MODEL_REVISION','82a37760796d32b1411fe092ab5d4e227313294b')
        self.processor=BlipProcessor.from_pretrained(model, revision=revision)
        self.model=BlipForConditionalGeneration.from_pretrained(model, revision=revision, use_safetensors=False).to('cpu').eval()

    def __call__(self, image):
        inputs=self.processor(images=image,return_tensors='pt').to('cpu')
        with self.torch.inference_mode():
            output=self.model.generate(**inputs,max_new_tokens=30,num_beams=1,do_sample=False)
        text=self.processor.decode(output[0],skip_special_tokens=True).strip()
        if not text:
            raise RuntimeError('Model generated an empty caption.')
        return text

@dataclass
class Result:
    filename: str
    caption: str = ''
    seconds: float = 0.0
    error: str = ''

class CaptionService:
    def __init__(self, metrics=None, model_factory: Callable=CaptionModel):
        self.metrics=metrics or Metrics()
        self.model_factory=model_factory
        self.model=None
        self.lock=threading.Lock()

    def load(self):
        with self.lock:
            if self.model is None:
                self.model=self.model_factory()
                self.metrics.model_ready.set(1)
                self.metrics.update_memory()

    @contextmanager
    def request(self, mode, client):
        if mode not in MODES or client not in CLIENTS:
            raise ValueError('Unknown mode or client category.')
        m=self.metrics
        start=time.perf_counter()
        m.active.labels(mode).inc()
        if mode=='bulk': m.bulk.inc()
        try:
            yield
        finally:
            m.active.labels(mode).dec()
            if mode=='bulk': m.bulk.dec()
            m.upload_duration.labels(mode).observe(time.perf_counter()-start)
            m.update_memory()

    def _image(self, data, name, mode, client):
        m=self.metrics
        start=time.perf_counter()
        operation='decode'
        try:
            image=decode_image(data)
            operation='model'
            self.load()
            operation='inference'
            # Serialize inference across users to bound CPU/RAM.
            with self.lock:
                m.inflight.inc()
                infer=time.perf_counter()
                try:
                    caption=self.model(image)
                finally:
                    elapsed=time.perf_counter()-infer
                    m.inflight.dec()
                    m.inference.labels(mode).observe(elapsed)
                    m.summary.labels(mode).observe(elapsed)
            m.images.labels(mode,'success',client).inc()
            return Result(name,caption,time.perf_counter()-start)
        except Exception as e:
            m.errors.labels(mode,operation,client).inc()
            m.images.labels(mode,'error',client).inc()
            # Detailed type is useful locally; never send file paths/client ids as labels.
            if isinstance(e,InputError): message=str(e)
            elif isinstance(e,MemoryError): message='Insufficient memory; reduce image or batch size.'
            else: message=f'{operation.capitalize()} failed ({type(e).__name__}). See server logs.'
            import logging
            logging.getLogger(__name__).exception('Caption failure: %s', operation)
            return Result(name,seconds=time.perf_counter()-start,error=message)
        finally:
            m.processing.labels(mode).observe(time.perf_counter()-start)
            m.update_memory()

    def single(self,data,name='image',client='interactive'):
        with self.request('single',client):
            result=self._image(data,name,'single',client)
            self.metrics.requests.labels('single','error' if result.error else 'success',client).inc()
            return result

    def bulk(self,data,client='interactive',progress=None):
        with self.request('bulk',client):
            try:
                archive,entries=zip_members(data)
            except (InputError,MemoryError):
                self.metrics.errors.labels('bulk','validation',client).inc()
                self.metrics.requests.labels('bulk','error',client).inc()
                raise
            self.metrics.batch.set(len(entries))
            self.metrics.batch_sizes.observe(len(entries))
            results=[]
            with archive:
                for i,item in enumerate(entries):
                    try:
                        raw=archive.read(item)
                        result=self._image(raw,item.filename,'bulk',client)
                    except Exception as e:
                        self.metrics.errors.labels('bulk','decode',client).inc()
                        self.metrics.images.labels('bulk','error',client).inc()
                        result=Result(item.filename,error=f'ZIP member unreadable ({type(e).__name__}).')
                    results.append(result)
                    if progress: progress(i+1,len(entries),result)
            self.metrics.requests.labels('bulk','error' if any(r.error for r in results) else 'success',client).inc()
            return results
