"""Real AT-SPI reads; table-cell state is unavailable rather than unsafe."""
import json
SOURCE = r'''
import json,time,pyatspi
from lxml import etree as E
from pyatspi import STATE_SHOWING,STATE_VISIBLE
settings=json.loads(SETTINGS_LITERAL)
ns={'st':'https://accessibility.ubuntu.example.org/ns/state','cp':'https://accessibility.ubuntu.example.org/ns/component','val':'https://accessibility.ubuntu.example.org/ns/value'}
started=time.monotonic();stats={'visited':0,'included':0,'pruned_not_showing':0,'pruned_geometry':0,'cell_states_unavailable':0,'errors':[],'capped':False,'scope':'actual focused application window','policy':'visible_a11y_v2_cell_geometry'}
clip_roles={'frame','dialog','window','tree','table','list','scroll-pane','viewport'}
def intersection(a,b):
 if a is None:return b
 if b is None:return a
 left,top=max(a[0],b[0]),max(a[1],b[1]);right,bottom=min(a[0]+a[2],b[0]+b[2]),min(a[1]+a[3],b[1]+b[3])
 return (left,top,max(0,right-left),max(0,bottom-top))
def walk(node,depth=0,clip=None):
 if stats['included']>=1200 or depth>50 or time.monotonic()-started>9:
  stats['capped']=True;return None
 stats['visited']+=1
 try:
  role=node.getRoleName().strip().replace(' ','-') or 'unknown'
  is_cell=role=='table-cell'
  # No page/label/model special cases: native GetState is unsafe on Qt cells.
  state=None if is_cell else node.getState()
  if state is not None and role!='application' and not(state.contains(STATE_SHOWING) and state.contains(STATE_VISIBLE)):
   stats['pruned_not_showing']+=1;return None
  attrs={'name':node.name or ''}
  if state is None:
   stats['cell_states_unavailable']+=1
   attrs['state_readback']='unavailable_table_cell_native_safety'
  else:
   for item in state.get_states():
    name=pyatspi.StateType._enum_lookup[item].split('_',1)[1].lower()
    attrs['{'+ns['st']+'}'+name]='true'
  rect=None
  try:
   rect=tuple(node.queryComponent().getExtents(pyatspi.XY_SCREEN))
   attrs['{'+ns['cp']+'}screencoord']=str(tuple(rect[:2]));attrs['{'+ns['cp']+'}size']=str(tuple(rect[2:]))
  except (NotImplementedError,AttributeError):pass
  if is_cell:
   visible=intersection(clip,rect)
   if rect is None or clip is None or rect[2]<=0 or rect[3]<=0 or visible[2]<=0 or visible[3]<=0:
    stats['pruned_geometry']+=1;return None
   attrs['visibility_source']='actual_extents_intersecting_showing_container'
   attrs['visible_bounds']=str(tuple(visible))
  child_clip=intersection(clip,rect) if role in clip_roles and rect and rect[2]>0 and rect[3]>0 else clip
  result=E.Element(role,attrib=attrs,nsmap=ns);stats['included']+=1
  try:
   text=node.queryText();value=text.getText(0,text.characterCount)
   if value:result.text=value.replace('\ufffc','').replace('\ufffd','')
  except (NotImplementedError,AttributeError):pass
  try:result.set('{'+ns['val']+'}value',str(node.queryValue().currentValue))
  except (NotImplementedError,AttributeError):pass
  for i,child in enumerate(node):
   if i>=1024:stats['capped']=True;break
   value=walk(child,depth+1,child_clip)
   if value is not None:result.append(value)
  return result
 except Exception as e:
  stats['errors'].append(type(e).__name__+': '+str(e)[:160]);return None
desktop=pyatspi.Registry.getDesktop(0);apps=[]
for app in desktop:
 try:
  if app.get_process_id()==settings['pid']:apps.append(app)
 except Exception:pass
root=E.Element('desktop-frame',nsmap=ns)
if len(apps)!=1:raise RuntimeError('Expected unique actual accessibility application')
app=apps[0];windows=[]
for child in app:
 try:
  if (child.name or '').strip()==settings['title'].strip():windows.append(child)
 except Exception:pass
if len(windows)!=1:raise RuntimeError('No unique accessible window matching actual focus title')
app_xml=E.SubElement(root,'application',name=app.name or '',nsmap=ns)
window=walk(windows[0])
if window is None:raise RuntimeError('Actual focused window unavailable from accessibility')
app_xml.append(window);stats['elapsed_seconds']=time.monotonic()-started
print(json.dumps({'xml':E.tostring(root,encoding='unicode'),'collection':stats},ensure_ascii=False))
'''
def guest_command(pid,title):
    source=SOURCE.replace('SETTINGS_LITERAL',repr(json.dumps({'pid':int(pid),'title':title})))
    return ('import subprocess,json\nr=subprocess.run(["/usr/bin/python3","-c",'+repr(source)+'],capture_output=True,text=True,timeout=12)\n'
            'if r.returncode:raise RuntimeError(r.stderr[-1000:])\nprint(r.stdout.strip())')
