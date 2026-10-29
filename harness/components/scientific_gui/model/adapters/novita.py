"""Native tools/tool_calls with a persistent, killable API-only HTTP worker."""
import json,multiprocessing,os,time
from pathlib import Path
from ..interface import Reply
from .chat_completions import ChatModel

class ProviderError(RuntimeError):
 def __init__(self,message,retryable=False):super().__init__(message);self.retryable=retryable

def worker(connection,key,endpoint):
 import requests
 session=requests.Session();session.headers.update({'Authorization':'Bearer '+key,'Content-Type':'application/json'})
 try:
  while True:
   item=connection.recv()
   if item is None:break
   payload,left=item;start=time.monotonic()
   try:
    response=session.post(endpoint,json=payload,timeout=(min(15,left/4),min(120,left*.75)))
    try:body=response.json()
    except ValueError:body={'invalid_json':True,'body':response.text[:2000].replace(key,'[redacted]')}
    body=json.loads(json.dumps(body,ensure_ascii=False).replace(key,'[redacted]'))
    connection.send({'http_status':response.status_code,'body':body,'worker_elapsed_seconds':time.monotonic()-start})
   except Exception as e:connection.send({'transport_error':str(e).replace(key,'[redacted]')[:1000],'worker_elapsed_seconds':time.monotonic()-start})
 except (EOFError,BrokenPipeError):pass
 finally:session.close();connection.close()

class NovitaModel(ChatModel):
 def __init__(self,config):
  super().__init__(config);self.process=None;self.attempts=0;self.seconds=0;self.usage={};self.logdir=None
 def bind_run(self,directory):
  self.logdir=Path(directory)
  for name in ('requests','responses'):(self.logdir/name).mkdir(exist_ok=True)
 def generate(self,messages,tools,timeout):
  deadline=time.monotonic()+timeout
  if self.process is None:
   key=os.environ.get(self.config.get('api_key_env','MODEL_API_KEY'))
   if not key:raise ProviderError('Missing model API key environment variable')
   context=multiprocessing.get_context('spawn');self.connection,child=context.Pipe()
   self.process=context.Process(target=worker,args=(child,key,self.endpoint),daemon=True);self.process.start();child.close()
  cfg=self.config;payload={'model':cfg['model'],**cfg.get('parameters',{}),'messages':messages,'tools':tools,'tool_choice':cfg.get('tool_choice','auto'),'parallel_tool_calls':False}
  self.attempts+=1;stem=f'{self.attempts:03d}'
  ledger=os.environ.get('COPASI_API_PREFLIGHT_LEDGER')
  if ledger:
   from filelock import FileLock
   path=Path(ledger)
   with FileLock(str(path)+'.lock',timeout=0):
    value=json.loads(path.read_text()) if path.exists() else {'attempts':0,'limit':10}
    if value['attempts']>=10:raise ProviderError('New-project short-loop request budget exhausted')
    value['attempts']+=1;path.write_text(json.dumps(value),encoding='utf-8')
  if self.logdir:(self.logdir/'requests'/f'{stem}.json').write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
  start=time.monotonic();left=deadline-start
  if left<=0:raise TimeoutError('API deadline before dispatch')
  self.connection.send((payload,left))
  if not self.connection.poll(max(0,deadline-time.monotonic())):
   self.seconds+=time.monotonic()-start;self.close()
   if self.logdir:(self.logdir/'responses'/f'{stem}.json').write_text(json.dumps({'hard_deadline':True,'elapsed_seconds':time.monotonic()-start}),encoding='utf-8')
   raise TimeoutError('Absolute API deadline; worker terminated')
  result=self.connection.recv();elapsed=time.monotonic()-start;self.seconds+=elapsed;result['elapsed_seconds']=elapsed
  if self.logdir:(self.logdir/'responses'/f'{stem}.json').write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
  if 'transport_error' in result:raise ProviderError(result['transport_error'],True)
  if result['http_status']!=200:raise ProviderError('Novita HTTP '+str(result['http_status']),result['http_status']==429 or result['http_status']>=500)
  body=result['body'];usage=body.get('usage') or {}
  for key in ('prompt_tokens','completion_tokens','total_tokens'):self.usage[key]=self.usage.get(key,0)+int(usage.get(key,0))
  try:message=body['choices'][0]['message']
  except (KeyError,IndexError,TypeError):raise ProviderError('Malformed provider response') from None
  calls=message.get('tool_calls') or [];actions=[]
  for call in calls:
   try:
    fn=call['function'];args=json.loads(fn['arguments'])
    if not isinstance(args,dict) or 'type' in args:raise ValueError()
    actions.append({'type':fn['name'],**args})
   except (ValueError,KeyError,TypeError):actions.append({'type':'invalid_native_arguments'})
  native={'role':'assistant','content':message.get('content') or None}
  if calls:native['tool_calls']=calls
  return Reply(actions,message.get('content') or '',usage,native)
 def close(self):
  if self.process:
   try:self.connection.send(None)
   except (EOFError,OSError):pass
   self.process.join(.15)
   if self.process.is_alive():self.process.terminate();self.process.join(1)
   self.connection.close();self.process=None
