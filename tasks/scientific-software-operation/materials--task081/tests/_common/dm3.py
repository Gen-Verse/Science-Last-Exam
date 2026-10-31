"""Bounded DM3 tag/data reader for native real microscopy images and profiles.

The tag container uses big-endian lengths/type descriptors and a declared data
endianness. This independently implemented reader handles primitive, string,
structure and array tags. Packed FFT/RGB images cannot masquerade as real data.
Format cross-check: openNCEM ncempy/io/dm.py, release v1.16. No library code is
vendored, and this reader does not execute scripts or deserialize Python objects.
"""
from pathlib import Path
import math,struct
import numpy as np

TYPES={2:'i2',3:'i4',4:'u2',5:'u4',6:'f4',7:'f8',8:'u1',9:'i1',10:'u1',11:'i8',12:'u8'}
IMAGE_TYPES={1:'i2',2:'f4',3:'c8',6:'u1',7:'i4',9:'i1',10:'u2',11:'u4',12:'f8',13:'c16'}

class Reader:
 def __init__(self,path):
  self.path=Path(path);self.file=self.path.open('rb');self.size=self.path.stat().st_size;self.tags=0
  try:
   if not 18<=self.size<=512_000_000:raise ValueError('DM3 file size is outside the evidence budget')
   version,total,endian=struct.unpack('>III',self.take(12))
   if version!=3 or endian not in {0,1}:raise ValueError('Save native DM3, not DM4/packed/display-only data')
   self.endian='<' if endian else '>';self.tree=self.group(0)
  except BaseException:
   self.file.close();raise
 def close(self):self.file.close()
 def take(self,count):
  if count<0 or count>self.size-self.file.tell():raise ValueError('Truncated DM3 data')
  data=self.file.read(count)
  if len(data)!=count:raise ValueError('Truncated DM3 data')
  return data
 def uint(self,fmt):return struct.unpack('>'+fmt,self.take(struct.calcsize('>'+fmt)))[0]
 def descriptor(self,info,index=0,depth=0):
  if depth>32 or index>=len(info):raise ValueError('Malformed DM3 type descriptor')
  kind=info[index];index+=1
  if kind in TYPES:return {'kind':kind,'size':np.dtype(TYPES[kind]).itemsize},index
  if kind==18:
   count=info[index];return {'kind':kind,'size':count},index+1
  if kind==15:
   name_length,count=info[index:index+2];index+=2
   if name_length or count>1000:raise ValueError('Unsupported named DM3 structure')
   members=[]
   for _ in range(count):
    if info[index]:raise ValueError('Unsupported named DM3 field')
    member,index=self.descriptor(info,index+1,depth+1);members.append(member)
   return {'kind':kind,'members':members,'size':sum(x['size'] for x in members)},index
  if kind==20:
   member,index=self.descriptor(info,index,depth+1);count=info[index];return {'kind':kind,'member':member,'count':count,'size':member['size']*count},index+1
  raise ValueError('Unsupported DM3 tag type '+str(kind))
 def data(self):
  if self.take(4)!=b'%%%%':raise ValueError('Invalid DM3 tag delimiter')
  count=self.uint('I')
  if not 1<=count<=10000:raise ValueError('Invalid DM3 descriptor size')
  info=struct.unpack('>'+str(count)+'I',self.take(4*count));descriptor,end=self.descriptor(info)
  if end!=len(info):raise ValueError('Trailing DM3 type information')
  size=descriptor['size'];offset=self.file.tell()
  if size>self.size-offset:raise ValueError('DM3 payload exceeds file')
  kind=descriptor['kind']
  if kind in TYPES:return np.frombuffer(self.take(size),dtype=self.endian+TYPES[kind])[0].item()
  if kind==18:return self.take(size).decode('utf-8',errors='replace')
  self.file.seek(size,1);return {'offset':offset,**descriptor}
 def group(self,depth):
  if depth>64:raise ValueError('DM3 nesting exceeds budget')
  self.take(2);count=self.uint('I');result={};self.tags+=count
  if self.tags>100000:raise ValueError('DM3 tag count exceeds budget')
  for index in range(count):
   kind=self.uint('B');length=self.uint('H');label=self.take(length).decode('latin1') if length else str(index)
   if label in result:raise ValueError('Duplicate DM3 tag name')
   if kind==20:value=self.group(depth+1)
   elif kind==21:value=self.data()
   else:raise ValueError('Unknown DM3 tag class')
   result[label]=value
  return result
 def string(self,value):
  if isinstance(value,str):return value.rstrip('\0')
  if isinstance(value,dict) and value.get('kind')==20 and value['member']['kind'] in {4,9,10}:
   self.file.seek(value['offset']);raw=self.take(value['size']);return raw.decode('utf-16-le' if value['member']['kind']==4 and self.endian=='<' else 'utf-16-be' if value['member']['kind']==4 else 'utf-8').rstrip('\0')
  return ''
 def images(self):
  found=[]
  def walk(node):
   if not isinstance(node,dict):return
   if 'ImageData' in node and isinstance(node['ImageData'],dict):found.append(node['ImageData'])
   for name,value in node.items():
    if name!='ImageData':walk(value)
  walk(self.tree);return found
 def real_image(self):
  valid=[]
  for item in self.images():
   code=item.get('DataType');dimensions=item.get('Dimensions',{});sizes=[int(dimensions[k]) for k in sorted(dimensions,key=lambda x:int(x))]
   if code not in IMAGE_TYPES or not 1<=len(sizes)<=2:continue
   if any(n<=0 or n>16384 for n in sizes):continue
   if np.dtype(IMAGE_TYPES[code]).kind=='c':continue
   payload=item.get('Data')
   if not isinstance(payload,dict) or payload.get('kind')!=20:continue
   count=math.prod(sizes);dtype=np.dtype(self.endian+IMAGE_TYPES[code])
   if payload['size']!=count*dtype.itemsize:raise ValueError('DM3 image data/shape mismatch')
   valid.append((count,item,sizes,dtype,payload))
  if not valid:raise ValueError('No real numeric DM3 image/profile')
  # Ignore the RGB thumbnail; reject ambiguous equally large scientific data.
  valid.sort(key=lambda x:x[0],reverse=True)
  if len(valid)>1 and valid[0][0]==valid[1][0]:raise ValueError('Save each required scientific image/profile as its own DM3')
  count,item,sizes,dtype,payload=valid[0];self.file.seek(payload['offset']);array=np.frombuffer(self.take(payload['size']),dtype=dtype).copy().reshape(tuple(reversed(sizes)))
  calibration=item.get('Calibrations',{}).get('Dimension',{});scales=[];units=[]
  for index in range(len(sizes)):
   axis=calibration.get(str(index),{});scales.append(float(axis.get('Scale',1)));units.append(self.string(axis.get('Units','')))
  if not np.isfinite(array).all() or not all(math.isfinite(s) and s>0 for s in scales):raise ValueError('Nonfinite image/calibration')
  return {'data':array,'pixel_size':list(reversed(scales)),'units':list(reversed(units)),'dtype':dtype.str,'offset':payload['offset'],'shape':list(array.shape)}

def read(path):
 reader=None
 try:reader=Reader(path);return reader.real_image()
 finally:
  if reader is not None:reader.close()
