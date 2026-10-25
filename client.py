"""Streamlit client for the CPU worker; HTTP errors become useful UI messages."""
import os
from dataclasses import fields
import requests
from captioning import Result, InputError

class CaptionClient:
    def __init__(self): self.url=os.getenv('CAPTION_WORKER_URL','http://127.0.0.1:8001')
    def _request(self,path,data,client,name=None):
        try:
            response=requests.post(self.url+path,data=data,params={'filename':name} if name else None,
                headers={'X-Client-Category':client,'Content-Type':'application/octet-stream'},timeout=(10,600))
            payload=response.json()
            if not response.ok: raise InputError(payload.get('error',f'Worker HTTP {response.status_code}'))
            return [Result(**r) for r in payload['results']]
        except requests.RequestException as e:
            raise InputError('CPU worker unavailable or timed out. Check backend logs and retry.') from e
    def single(self,data,name='image',client='interactive'):
        return self._request('/single',data,client,name)[0]
    def bulk(self,data,client='interactive',progress=None):
        results=self._request('/bulk',data,client)
        if progress:
            for i,r in enumerate(results): progress(i+1,len(results),r)
        return results
