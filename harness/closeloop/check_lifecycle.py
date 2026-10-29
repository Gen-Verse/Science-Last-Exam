"""Timeout/cancel isolation check; no model or scientific experiment."""
import json,os,subprocess,tempfile,time
from pathlib import Path
from lab.backend import command,BudgetTimeout,Cancelled
with tempfile.TemporaryDirectory(prefix='sle-lifecycle-') as d:
    root=Path(d);case=root/'case';case.mkdir()
    peer=subprocess.Popen(['sleep','20'],start_new_session=True)
    try:
        start=time.monotonic()
        try:command(['bash','-c','sleep 20 & wait'],case,root/'timeout.log',time.monotonic()+1,root/'cancel')
        except BudgetTimeout:pass
        else:raise AssertionError('Timeout was not enforced')
        assert peer.poll() is None
        elapsed=time.monotonic()-start;assert elapsed<8
        (root/'cancel').touch()
        try:command(['sleep','20'],case,root/'cancel.log',time.monotonic()+10,root/'cancel')
        except Cancelled:pass
        else:raise AssertionError('Cancel was not enforced')
        assert peer.poll() is None
        print(json.dumps({'timeout_caught':True,'cancellation_caught':True,'unrelated_process_alive':True,'timeout_wall_seconds':elapsed}))
    finally:
        peer.terminate();peer.wait()
