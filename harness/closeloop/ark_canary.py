"""One bounded live check of the explicit Ark plan route; no retries/fallbacks."""
import json,os,time
from pathlib import Path
import httpx
root=Path(__file__).resolve().parents[2]/'.local/closeloop/providers'
root.mkdir(parents=True,exist_ok=True)
key=os.environ.get('SLE_ARK_API_KEY')
if not key and os.environ.get('SLE_ARK_KEY_FILE'):key=Path(os.environ['SLE_ARK_KEY_FILE']).read_text().strip()
if not key:raise SystemExit('Set SLE_ARK_API_KEY or SLE_ARK_KEY_FILE on the controller.')
base='https://ark.cn-beijing.volces.com/api/plan/v3';model='deepseek-v4.1-flash'
receipt={'provider':'Ark Agent Plan','base_url':base,'requested_model':model,'started_at':time.time(),'request_cap':1,'max_output_tokens':64,'shared_project_pause_modified':False}
try:
    with httpx.Client(timeout=45,trust_env=False,follow_redirects=False) as client:
        response=client.post(base+'/responses',headers={'Authorization':'Bearer '+key},json={'model':model,'input':'Reply OK only.','max_output_tokens':64})
    try:data=response.json()
    except ValueError:data={}
    receipt.update(http_status=response.status_code,returned_model=data.get('model'),response_status=data.get('status'),usage=data.get('usage'),error=data.get('error'))
    receipt['available']=response.status_code==200 and data.get('model')==model
    receipt['category']='available' if receipt['available'] else 'provider_api_failure'
except httpx.HTTPError as e:
    receipt.update(available=False,category='provider_transport_failure',error={'type':type(e).__name__,'message':str(e)})
receipt['finished_at']=time.time()
clean=json.dumps(receipt,indent=2).replace(key,'[REDACTED]')+'\n'
(root/'ark_canary.json').write_text(clean)
pause=Path(os.environ.get('SLE_ARK_PROVIDER_PAUSE_FILE',str(root/'ark-unavailable.json')))
if not receipt['available']:pause.write_text(json.dumps({'category':receipt['category'],'canary':'ark_canary.json','checked_at':receipt['finished_at']})+'\n')
elif pause.exists():pause.unlink()
print(clean)
