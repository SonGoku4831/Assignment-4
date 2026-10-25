"""Generate real photographic fixtures and a 10-image ZIP; never fabricate captions."""
import io
import json
import zipfile
from pathlib import Path
import requests
from PIL import Image, ImageEnhance
ROOT=Path(__file__).resolve().parents[1]
def main():
    dest=ROOT/'samples/generated'; dest.mkdir(parents=True,exist_ok=True)
    source='https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/sklearn/datasets/images/flower.jpg'
    credit='https://raw.githubusercontent.com/scikit-learn/scikit-learn/main/sklearn/datasets/images/README.txt'
    r=requests.get(source,timeout=45); r.raise_for_status()
    (dest/'flower.jpg').write_bytes(r.content)
    c=requests.get(credit,timeout=45); c.raise_for_status()
    (dest/'SOURCE.txt').write_text(source+'\n\n'+c.text)
    image=Image.open(io.BytesIO(r.content)).convert('RGB')
    with zipfile.ZipFile(dest/'bulk-10.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for i in range(10):
            varied=ImageEnhance.Brightness(image).enhance(.8+.04*i)
            f=io.BytesIO(); varied.save(f,format='JPEG',quality=90)
            archive.writestr(f'flower-{i+1:02}.jpg',f.getvalue())
    (dest/'corrupt.jpg').write_bytes(b'This is deliberately not an image.')
    for name,entries in [('empty.zip',[]),('corrupt-image.zip',[('good.jpg',r.content),('bad.jpg',b'corrupt')])]:
        with zipfile.ZipFile(dest/name,'w') as archive:
            for fn,data in entries: archive.writestr(fn,data)
    print(json.dumps({'single':str(dest/'flower.jpg'),'bulk':str(dest/'bulk-10.zip'),'images':10}))
if __name__=='__main__': main()
