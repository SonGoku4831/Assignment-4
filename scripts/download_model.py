"""Download pinned public BLIP weights without running inference or remote code."""
import os
import hashlib
import json
from pathlib import Path
from huggingface_hub import snapshot_download
ROOT=Path(__file__).resolve().parents[1]
os.environ.setdefault('HF_HUB_DISABLE_XET','1')
if __name__=='__main__':
    path=snapshot_download('Salesforce/blip-image-captioning-base',revision='82a37760796d32b1411fe092ab5d4e227313294b',
        cache_dir=str(ROOT/'.cache/huggingface/hub'),
        allow_patterns=['*.json','vocab.txt','pytorch_model.bin'])
    weights=Path(path)/'pytorch_model.bin'
    digest=hashlib.file_digest(weights.open('rb'),'sha256').hexdigest()
    expected='d6638651a5526cc2ede56f2b5104d6851b0755816d220e5e046870430180c767'
    if digest != expected: raise RuntimeError('Pinned model SHA256 mismatch')
    evidence={'snapshot':path,'sha256':digest,'bytes':weights.stat().st_size,'verified':True}
    (ROOT/'artifacts/model-integrity.json').write_text(json.dumps(evidence,indent=2))
    print(json.dumps(evidence))
