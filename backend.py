"""Local CPU inference worker. Metrics start before any browser connects."""
import dataclasses
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs
from captioning import CaptionService, Metrics, InputError, MAX_ZIP_BYTES, MAX_IMAGE_BYTES

class WorkerServer(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,service):
        super().__init__(address,Handler)
        self.service=service
        self.slots=threading.BoundedSemaphore(2)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args): logging.info(fmt,*args)
    def reply(self,status,data):
        raw=json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)
    def do_GET(self):
        if self.path=='/health':
            self.reply(200,{'status':'ok','device':'cpu','model_ready':self.server.service.model is not None})
        else: self.reply(404,{'error':'Unknown endpoint'})
    def do_POST(self):
        path=urlsplit(self.path)
        if path.path not in ('/single','/bulk'):
            self.reply(404,{'error':'Unknown endpoint'}); return
        client=self.headers.get('X-Client-Category','interactive')
        if client not in ('interactive','demonstration','test'):
            self.reply(400,{'error':'Unknown client category'}); return
        try: size=int(self.headers.get('Content-Length','0'))
        except ValueError: size=0
        limit=MAX_IMAGE_BYTES if path.path=='/single' else MAX_ZIP_BYTES
        if not 0<size<=limit:
            self.reply(413,{'error':'Missing, empty, or oversized request body'}); return
        if not self.server.slots.acquire(blocking=False):
            self.reply(429,{'error':'Worker busy. Retry after current uploads complete.'}); return
        try:
            self.connection.settimeout(30)
            data=self.rfile.read(size)
            if len(data)!=size: raise InputError('Incomplete upload')
            if path.path=='/single':
                name=parse_qs(path.query).get('filename',['image'])[0][:255]
                results=[self.server.service.single(data,name,client)]
            else: results=self.server.service.bulk(data,client)
            self.reply(200,{'results':[dataclasses.asdict(r) for r in results]})
        except InputError as e: self.reply(400,{'error':str(e)})
        except (MemoryError,TimeoutError): self.reply(503,{'error':'Worker resource limit or upload timeout'})
        finally: self.server.slots.release()

def main():
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    metrics=Metrics(); metrics.serve(8000)
    service=CaptionService(metrics)
    WorkerServer(('127.0.0.1',8001),service).serve_forever()

if __name__=='__main__': main()
