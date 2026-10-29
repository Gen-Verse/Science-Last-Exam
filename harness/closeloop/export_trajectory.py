"""Convert recorded visible Codex events to ATIF; never synthesize a rollout."""
import argparse,hashlib,json
from collections import Counter
from pathlib import Path
from harbor.models.trajectories.trajectory import Trajectory

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def canonical(x):return json.dumps(x,sort_keys=True,ensure_ascii=False)

def export(trial):
    result=json.loads((trial/'result.json').read_text());meta=result['agent_result']['metadata']
    events=[json.loads(s) for s in (trial/'agent/codex_events.jsonl').read_text().splitlines()]
    completed={};started=[];requests={};settings=[]
    for e in events:
        p=e.get('params',{});kind=e.get('method')
        if kind=='item/started':started.append(p['item']['id'])
        if kind=='item/completed':completed[p['item']['id']]=p['item']
        if kind=='item/tool/call':requests[p['callId']]=p
        if kind=='thread/settings/updated':
            settings.append({k:p['threadSettings'].get(k) for k in ['model','effort']})
    steps=[];observed=[];incomplete=[]
    for iid in started:
        if iid not in completed:incomplete.append(iid);continue
        item=completed[iid];kind=item['type']
        if kind=='reasoning':continue
        assert kind in ['userMessage','agentMessage','dynamicToolCall'],kind
        step={'step_id':len(steps)+1,'source':'user' if kind=='userMessage' else 'agent','message':'','extra':{'codex_item_id':iid,'codex_item_type':kind}}
        if kind=='userMessage':step['message']='\n'.join(x['text'] for x in item['content'] if x['type']=='text')
        elif kind=='agentMessage':step['message']=item.get('text','')
        else:
            req=requests[iid];args=item['arguments'];args=json.loads(args) if isinstance(args,str) else args
            rargs=req['arguments'];rargs=json.loads(rargs) if isinstance(rargs,str) else rargs
            assert args==rargs and item['tool']==req['tool']=='run_command'
            content='\n'.join(c['text'] for c in item['contentItems'] if c['type']=='inputText')
            output=json.loads(content);observed.append((canonical(args),canonical(output)))
            step['tool_calls']=[{'tool_call_id':iid,'function_name':'run_command','arguments':args}]
            step['observation']={'results':[{'source_call_id':iid,'content':content}]}
        if kind!='userMessage':step['model_name']=meta['requested_model'];step['reasoning_effort']=meta['reasoning_effort']
        steps.append(step)
    logged=[]
    for line in (trial/'agent/tool_calls.jsonl').read_text().splitlines():
        c=json.loads(line);args=c['arguments'];args=json.loads(args) if isinstance(args,str) else args
        logged.append((canonical(args),canonical(c['output'])))
    if not incomplete:assert Counter(observed)==Counter(logged)
    assert settings and all(s['model']==meta['requested_model'] for s in settings)
    usage=result['agent_result']
    t={'schema_version':'ATIF-v1.6','session_id':meta['thread_id'],'agent':{'name':'sle-hosted-codex','version':'0.1.0','model_name':meta['requested_model']},
       'steps':steps,'notes':'Export of visible user/assistant messages and recorded dynamic tool exchanges. Private reasoning omitted. No invented steps, token IDs or log probabilities. Terminal grading was external.',
       'final_metrics':{'total_prompt_tokens':usage.get('n_input_tokens'),'total_completion_tokens':usage.get('n_output_tokens'),'total_cached_tokens':usage.get('n_cache_tokens'),'total_steps':len(steps)},
       'extra':{'task_checksum':result['task_checksum'],'source_events_sha256':sha(trial/'agent/codex_events.jsonl'),'original_tool_call_ids_preserved':True,'tool_observations_cross_checked':not incomplete,'incomplete_item_ids':incomplete,'confirmed_model_settings':settings,'policy_completed':meta.get('completed',False),'trial_exception_type':(result.get('exception_info') or {}).get('exception_type')}}
    checked=Trajectory.model_validate(t)
    (trial/'agent/trajectory.json').write_text(checked.model_dump_json(indent=2)+'\n')
    print(json.dumps({'trial':str(trial),'steps':len(steps),'tools':len(observed),'model':meta['requested_model'],'incomplete_items':len(incomplete)}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('trial',type=Path);args=p.parse_args();export(args.trial)
