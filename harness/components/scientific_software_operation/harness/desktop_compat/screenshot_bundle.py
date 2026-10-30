"""One real screen capture: unmarked pixels for metrics, native cursor for agent."""
from harness.timeouts import scaled_timeout
import base64
import json
import time

SOURCE=r'''
import pyautogui,io,base64,json,time,sys
from PIL import Image
_begin=time.time_ns()
_base=pyautogui.screenshot()
_captured=time.time_ns()
_marked=_base.copy()
_overlay=None
try:
 sys.path.insert(0,_controller_dir)
 from pyxcursor import Xcursor
 _cursor=Xcursor()
 _shape=Image.fromarray(_cursor.getCursorImageArrayFast())
 _x,_y=pyautogui.position()
 _marked.paste(_shape,(_x,_y),_shape)
 _overlay={'position':[_x,_y],'size':list(_shape.size),'source':'Actual Xcursor image and current pointer position; same overlay as controller'}
except Exception as _e:_overlay={'unavailable':type(_e).__name__+': '+str(_e)}
def _png(im):
 _b=io.BytesIO();im.save(_b,format='PNG');return base64.b64encode(_b.getvalue()).decode()
print(json.dumps({'unmarked_png':_png(_base),'marked_png':_png(_marked),
 'capture':{'schema':1,'same_capture':True,'capture_begin_ns':_begin,'capture_end_ns':_captured,
 'source':'Unmodified pyautogui.screenshot pixels before cursor compositing','cursor':_overlay}}))
'''

def capture(backend):
    source='_controller_dir='+repr(getattr(backend,'guest_controller_dir','/home/user/server'))+'\n'+SOURCE
    response=backend.transport.execute(source,min(backend.budget.deadline,time.monotonic()+scaled_timeout(8)),read_only=True)
    value=json.loads(response['output'].strip().splitlines()[-1])
    return base64.b64decode(value['marked_png'],validate=True),base64.b64decode(value['unmarked_png'],validate=True),value['capture']
