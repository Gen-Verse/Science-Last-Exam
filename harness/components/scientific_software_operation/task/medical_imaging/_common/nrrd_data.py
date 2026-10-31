"""Read scalar/segmentation NRRDs without trusting cached measurements."""
import gzip
import math
from pathlib import Path
import re
import numpy as np

TYPES = {'uchar':'u1','unsigned char':'u1','uint8':'u1','char':'i1','int8':'i1',
         'short':'i2','short int':'i2','int16':'i2','ushort':'u2','unsigned short':'u2',
         'uint16':'u2','int':'i4','int32':'i4','uint':'u4','unsigned int':'u4',
         'uint32':'u4','float':'f4','double':'f8'}


def read(path_or_bytes):
    raw = path_or_bytes if isinstance(path_or_bytes, bytes) else Path(path_or_bytes).read_bytes()
    match = re.search(b'\r?\n\r?\n', raw)
    if match is None:
        raise ValueError('Missing NRRD header delimiter')
    lines = raw[:match.start()].decode('utf-8').splitlines()
    if not re.fullmatch('NRRD000[1-5]', lines[0]):
        raise ValueError('Invalid NRRD magic')
    fields = {}
    for line in lines[1:]:
        if not line or line.startswith('#'):
            continue
        key, value = line.split(':', 1)
        if key.lower() in fields:
            raise ValueError('Duplicate NRRD field')
        fields[key.lower()] = value.lstrip('=').strip()
    if 'data file' in fields or 'datafile' in fields:
        raise ValueError('Detached data is outside the submission contract')
    sizes = tuple(map(int, fields['sizes'].split()))
    if int(fields['dimension']) != len(sizes) or len(sizes) not in {3,4} or min(sizes) < 1 or math.prod(sizes) > 100000000:
        raise ValueError('Invalid NRRD dimensions')
    if fields.get('endian','little') not in {'little','big'}:raise ValueError('Invalid NRRD byte order')
    endian = '<' if fields.get('endian','little') == 'little' else '>'
    dtype = np.dtype(endian + TYPES[fields['type'].lower()])
    payload = raw[match.end():]
    encoding = fields.get('encoding','raw').lower()
    if encoding in {'gzip','gz'}:
        payload = gzip.decompress(payload)
    if encoding in {'ascii','text','txt'}:
        values = np.fromstring(payload.decode('ascii'), sep=' ', dtype=dtype)
    elif encoding in {'raw','gzip','gz'}:
        if len(payload) != math.prod(sizes)*dtype.itemsize:
            raise ValueError('NRRD payload size mismatch')
        values = np.frombuffer(payload,dtype=dtype)
    else:
        raise ValueError('Unsupported NRRD encoding')
    if values.size != math.prod(sizes) or not np.isfinite(values).all():
        raise ValueError('Invalid NRRD voxel data')
    directions = re.findall(r'none|\([^)]*\)', fields['space directions'], flags=re.I)
    if len(directions) != len(sizes):
        raise ValueError('Invalid space directions')
    list_axes = [i for i, value in enumerate(directions) if value.lower()=='none']
    if len(list_axes) != len(sizes)-3:
        raise ValueError('Expected three spatial axes')
    matrix = np.array([[float(x) for x in value.strip('()').split(',')] for value in directions if value.lower()!='none']).T
    origin = np.array([float(x) for x in fields['space origin'].strip('()').split(',')])
    space = fields.get('space','').lower()
    if space in {'right-anterior-superior','ras'}:
        flip = np.diag([-1.,-1.,1.]);matrix=flip@matrix;origin=flip@origin
    elif space not in {'left-posterior-superior','lps'}:
        raise ValueError('Declare an LPS or RAS physical space')
    if matrix.shape!=(3,3) or origin.shape!=(3,) or not np.isfinite(matrix).all() or abs(np.linalg.det(matrix))<1e-12:
        raise ValueError('Invalid physical geometry')
    return {'data':values.reshape(sizes,order='F'),'matrix':matrix,'origin':origin,
            'fields':fields,'list_axis':list_axes[0] if list_axes else None}


def same_grid(a,b):
    return a['data'].shape==b['data'].shape and np.allclose(a['matrix'],b['matrix'],rtol=0,atol=1e-6) and np.allclose(a['origin'],b['origin'],rtol=0,atol=1e-6)


def dice(a,b):
    a,b=np.asarray(a,bool),np.asarray(b,bool)
    denominator=int(a.sum()+b.sum())
    return 2*int(np.logical_and(a,b).sum())/denominator if denominator else 0.


def segmentation(path, reference, names):
    item=read(path);fields=item['fields'];ids=sorted({int(m.group(1)) for key in fields if (m:=re.fullmatch(r'segment(\d+)_name',key))})
    if len(ids)!=len(names) or len({fields[f'segment{i}_name'] for i in ids})!=len(ids):
        raise ValueError('Wrong segmentation membership')
    if not np.allclose(item['matrix'],reference['matrix'],rtol=0,atol=1e-6):
        raise ValueError('Segmentation physical axes differ')
    # Native Slicer may crop a .seg.nrrd. Its physical origin, not an untrusted
    # extent tag, locates the crop on the reference grid. Re-expand with zero.
    shift=np.linalg.solve(reference['matrix'],item['origin']-reference['origin'])
    offset=np.rint(shift).astype(int)
    if not np.allclose(shift,offset,rtol=0,atol=1e-5):raise ValueError('Segmentation is not aligned to the source voxel grid')
    output={}
    for i in ids:
        name=fields[f'segment{i}_name'];layer=int(fields.get(f'segment{i}_layer',0));value=int(fields.get(f'segment{i}_labelvalue',i+1))
        if name not in names or value<=0:
            raise ValueError('Unknown segment name or label')
        data=item['data']
        if item['list_axis'] is not None:
            if not 0<=layer<data.shape[item['list_axis']]:raise ValueError('Invalid segment layer')
            data=np.take(data,layer,axis=item['list_axis'])
        elif layer!=0:raise ValueError('A scalar labelmap has one layer')
        end=offset+np.array(data.shape)
        if np.any(offset<0) or np.any(end>np.array(reference['data'].shape)):raise ValueError('Segmentation extends outside source geometry')
        mask=np.zeros(reference['data'].shape,dtype=bool)
        mask[tuple(slice(int(a),int(b)) for a,b in zip(offset,end))]=data==value
        output[name]=mask
    return output


def write(path, data, matrix=None, origin=None, extra=None):
    data=np.asarray(data,dtype=np.uint8 if data.dtype==bool else data.dtype)
    code=data.dtype.str[1:];kind={v:k for k,v in TYPES.items()}[code]
    matrix=np.eye(3) if matrix is None else np.asarray(matrix);origin=np.zeros(3) if origin is None else np.asarray(origin)
    vector=lambda values:'('+','.join(format(float(x),'.12g') for x in values)+')'
    header=['NRRD0005','type: '+kind,'dimension: 3','sizes: '+' '.join(map(str,data.shape)),
            'space: left-posterior-superior','space directions: '+' '.join(vector(matrix[:,i]) for i in range(3)),
            'space origin: '+vector(origin),'endian: little','encoding: gzip']
    header.extend(f'{key}:={value}' for key,value in (extra or {}).items())
    Path(path).write_bytes(('\n'.join(header)+'\n\n').encode()+gzip.compress(data.astype(data.dtype.newbyteorder('<')).tobytes(order='F'),mtime=0))
