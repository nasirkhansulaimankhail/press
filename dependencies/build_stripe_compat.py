"""Build the pinned legacy Stripe API wheel with a Python 3.14-compatible six.

Inputs are official PyPI wheels pinned by URL and SHA256. This patches no active
environment. Runtime API code and request/API-version behavior remain 2.56.0.
"""
from pathlib import Path
import base64,csv,hashlib,io,json,sys,urllib.request,zipfile

root=Path(__file__).resolve().parent
sources=json.loads((root/'stripe-compat-sources.json').read_text())
def download(name):
    source=sources[name]
    payload=urllib.request.urlopen(source['url'],timeout=90).read()
    assert hashlib.sha256(payload).hexdigest()==source['sha256'],name
    return zipfile.ZipFile(io.BytesIO(payload))

with download('stripe') as stripe,download('six') as six:
    members={name:stripe.read(name) for name in stripe.namelist() if not name.endswith('/')}
    members['stripe/six.py']=six.read('six.py')
version='2.56.0+univentures.1'
old='stripe-2.56.0.dist-info/'
new=f'stripe-{version}.dist-info/'
members={name.replace(old,new,1):data for name,data in members.items() if not name.endswith('/RECORD')}
metadata=new+'METADATA'
assert b'Version: 2.56.0\n' in members[metadata]
members[metadata]=members[metadata].replace(b'Version: 2.56.0\n',f'Version: {version}\n'.encode(),1)
record=io.StringIO();writer=csv.writer(record,lineterminator='\n')
for name,data in sorted(members.items()):
    digest=base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode()
    writer.writerow([name,'sha256='+digest,len(data)])
writer.writerow([new+'RECORD','',''])
members[new+'RECORD']=record.getvalue().encode()
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
wheel=out/f'stripe-{version}-py2.py3-none-any.whl'
with zipfile.ZipFile(wheel,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
    for name,data in sorted(members.items()):
        info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED
        info.external_attr=0o644<<16
        archive.writestr(info,data,compresslevel=9)
manifest={'wheel':wheel.name,'sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),'upstream_sdk':'2.56.0','distribution_version':version,'inputs':sources,'changed_runtime_file':'stripe/six.py'}
(out/'stripe-compat-wheel.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(wheel.name,manifest['sha256'])
