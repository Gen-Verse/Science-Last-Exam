"""Canonical source-model structure, independent of temporary COPASI keys."""
import re
NS="http://www.copasi.org/static/schema"
def q(s):return "{"+NS+"}"+s
def scientific_structure(root):
 """Stable SBML identifiers, expressions and reaction mappings; no temporary keys."""
 mapping={x.get('COPASIkey'):x.get('SBMLid') for x in root.find(q('SBMLReference'))}
 model=root.find(q('Model'));mapping[model.get('key')]='MODEL'
 for function in root.find(q('ListOfFunctions')):
  mapping[function.get('key')]='FUNCTION:'+function.get('name')
  for x in function.iter():
   if x.get('key') and x is not function:mapping[x.get('key')]='FUNCTION_PARAMETER:'+function.get('name')+'/'+x.get('name','')
 for reaction in model.find(q('ListOfReactions')):
  for x in reaction.iter():
   if x.get('key') and x.get('key') not in mapping:mapping[x.get('key')]='LOCAL:'+mapping[reaction.get('key')]+'/'+x.get('name','')
 def text(value):
  value=value or ''
  value=re.sub(r'Model=[^,<>]+','Model=MODEL',value)
  return mapping.get(value,value)
 def canonical(node):
  tag=node.tag.rsplit('}',1)[-1]
  attrs={k:text(v) for k,v in node.attrib.items() if k not in ('key','name')}
  for k,v in list(attrs.items()):
   try:attrs[k]=float(v)
   except ValueError:pass
  return [tag,attrs,text(node.text).strip(),[canonical(x) for x in node if x.tag not in (q('MiriamAnnotation'),q('Comment'))]]
 states={}
 for parent_name in ('ListOfMetabolites','ListOfModelValues'):
  for node in model.find(q(parent_name)):
   sid=mapping[node.get('key')]
   states[sid]={'type':node.get('simulationType'),'initial_expression':text(node.findtext(q('InitialExpression'))).strip(),'expression':text(node.findtext(q('Expression'))).strip()}
 return {'states':states,'reactions':{mapping[x.get('key')]:canonical(x) for x in model.find(q('ListOfReactions'))}}
