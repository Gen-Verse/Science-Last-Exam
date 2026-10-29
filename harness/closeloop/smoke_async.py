"""Regression smoke of asynchronous execution and post-exit raw hashes."""
import hashlib,json,os,time
from pathlib import Path
from lab import store
from lab.task_cli import submit,snapshot
start=time.monotonic()
r=submit({'hypothesis':'Asynchronous 3D solver execution preserves an immutable scientific hash index.',
          'predicted_observation':'The solver reaches 0.05 s and all indexed hashes still match after the worker prints its final output.',
          'rationale':'Regression for worker stdout changing after index generation; this is an engineering fixture.'},True)
pid,status=os.waitpid(r['worker_pid'],0)
assert status==0,(pid,status)
snapshot();run=store.run(r['id']);assert run['status']=='completed',run
root=store.STATE/'runs'/r['id'];index=json.loads((root/'raw-index.json').read_text())
assert (root/'worker.log').stat().st_size>0
assert 'worker.log' not in {x['path'] for x in index}
assert all(hashlib.sha256((root/x['path']).read_bytes()).hexdigest()==x['sha256'] for x in index)
receipt={'run_id':r['id'],'task_version':'0.1.1','status':run['status'],'wall_seconds':time.monotonic()-start,'worker_stdout_preserved':True,'post_exit_index_verified':True,'indexed_files':len(index),'summary':run['summary']}
Path('/workspace/output/async-smoke.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({k:v for k,v in receipt.items() if k!='summary'},indent=2))
