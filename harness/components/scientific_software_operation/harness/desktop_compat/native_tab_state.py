"""Read-only native Qt tab facts, matched by current screen geometry, never labels."""
from harness.timeouts import scaled_timeout
import json
import time

SOCKET = '/home/user/copasi_bench/runtime/native_statefix/tabs.sock'
SOURCE = r'''
import socket,struct,json,time
_socket=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);_socket.settimeout(2)
try:
 _socket.connect(_path)
 _peer=struct.unpack('3i',_socket.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
 if _peer[0]!=_pid:raise RuntimeError('Native observer socket belongs to another process')
 _socket.sendall(b'snapshot\n');_body=b''
 while not _body.endswith(b'\n'):
  _part=_socket.recv(65536)
  if not _part:break
  _body+=_part
  if len(_body)>524288:raise RuntimeError('Native observer response exceeds limit')
 _data=json.loads(_body)
 if _data.get('pid')!=_pid or _data.get('qt_runtime')!='6.9.3':raise RuntimeError('Native observer identity/version mismatch')
 if abs(time.time()*1000-_data['sample_ms'])>1500:raise RuntimeError('Stale native widget state')
 print(json.dumps({'available':True,'peer_pid':_peer[0],'peer_uid':_peer[1],'snapshot':_data}))
except (OSError,RuntimeError,ValueError,KeyError) as _e:
 print(json.dumps({'available':False,'error':type(_e).__name__+': '+str(_e)}))
finally:_socket.close()
'''

def collect(backend):
    source='_path='+repr(SOCKET)+'\n_pid='+str(backend.pid)+'\n'+SOURCE
    response=backend.transport.execute(source,min(backend.budget.deadline,time.monotonic()+scaled_timeout(4)),read_only=True)
    return json.loads(response['output'].strip().splitlines()[-1])

def merge(tree, native, active_window):
    matches=conflicts=unknown=0
    tabs=[]
    if native.get('available'):
        for bar in native['snapshot'].get('bars',[]):
            if str(bar['window_id'])==str(active_window):
                tabs.extend(t for t in bar['tabs'] if t.get('visible'))
    for node in tree.get('nodes',[]):
        if node.get('role')!='page-tab':continue
        attrs=node['attributes']
        candidates=[t for t in tabs if t['bounds']==node.get('bounds')]
        attrs['atspi_enabled_reported']=attrs.pop('state:enabled', 'unknown')
        if len(candidates)==1:
            actual=candidates[0]
            enabled=str(actual['enabled']).lower()
            conflicts+=attrs['atspi_enabled_reported']!=enabled
            attrs.update({'state:enabled':enabled,'state_source':'Qt public QTabBar::isTabEnabled',
                          'native_tab_enabled':str(actual['tab_enabled']).lower(),
                          'native_parent_enabled':str(actual['bar_enabled']).lower(),
                          'native_match':'unique current global bounds and owning window'})
            matches+=1
        else:
            attrs.update(state_readback='native_tab_state_unavailable',state_source='unknown')
            unknown+=1
    return {'available':native.get('available',False),'matched_tabs':matches,'atspi_conflicts':conflicts,
            'unmatched_tabs':unknown,'error':native.get('error'),
            'source':'Read-only GUI-thread Qt getters; raw AT-SPI retained separately',
            'coordinate_or_label_inference':False}
