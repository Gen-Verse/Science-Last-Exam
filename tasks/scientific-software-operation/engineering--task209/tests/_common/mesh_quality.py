"""Symmetric, tolerance-bounded triangle-surface comparison without triangulation identity."""
import math
import numpy as np
from scipy.spatial import cKDTree


def arrays(path):
 with np.load(path,allow_pickle=False) as source:vertices=source['vertices'];indices=source['triangles']
 if vertices.ndim!=2 or vertices.shape[1]!=3 or indices.ndim!=2 or indices.shape[1]!=3 or not len(indices):raise ValueError('Invalid mesh arrays')
 if len(indices)>2_000_000 or not np.issubdtype(indices.dtype,np.integer) or indices.min()<0 or indices.max()>=len(vertices) or not np.isfinite(vertices).all():raise ValueError('Invalid or oversized triangle mesh')
 triangles=vertices[indices].astype(float);area=np.linalg.norm(np.cross(triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0]),axis=1)/2
 if np.any(area<1e-12):raise ValueError('Degenerate triangle')
 return triangles,float(area.sum())

def point_triangle_distance_squared(points,triangles):
 a,b,c=triangles[:,0],triangles[:,1],triangles[:,2];ab=b-a;ac=c-a;ap=points-a
 d00=np.einsum('ij,ij->i',ab,ab);d01=np.einsum('ij,ij->i',ab,ac);d11=np.einsum('ij,ij->i',ac,ac);d20=np.einsum('ij,ij->i',ap,ab);d21=np.einsum('ij,ij->i',ap,ac)
 den=d00*d11-d01*d01;v=(d11*d20-d01*d21)/den;w=(d00*d21-d01*d20)/den;normal=np.cross(ab,ac)
 result=(np.einsum('ij,ij->i',ap,normal)**2)/np.einsum('ij,ij->i',normal,normal)
 inside=(v>=0)&(w>=0)&(v+w<=1)
 edge_distance=np.full(len(points),np.inf)
 for left,right in [(a,b),(b,c),(c,a)]:
  delta=right-left;t=np.clip(np.einsum('ij,ij->i',points-left,delta)/np.einsum('ij,ij->i',delta,delta),0,1);diff=points-(left+t[:,None]*delta);edge_distance=np.minimum(edge_distance,np.einsum('ij,ij->i',diff,diff))
 return np.where(inside,result,edge_distance)


def index(triangles,tolerance):
 centers=triangles.mean(axis=1);radii=np.max(np.linalg.norm(triangles-centers[:,None,:],axis=2),axis=1);classes=np.floor(np.log2(np.maximum(radii,tolerance/8))).astype(int)
 result=[]
 for bucket in sorted(set(classes)):
  ids=np.flatnonzero(classes==bucket);result.append((cKDTree(centers[ids]),triangles[ids],centers[ids],radii[ids],float(radii[ids].max())))
 return result

def covered(points,buckets,distance):
 valid=np.zeros(len(points),bool)
 for tree,triangles,centers,radii,maximum in buckets:
  unresolved=np.flatnonzero(~valid)
  if not len(unresolved):break
  neighborhoods=tree.query_ball_point(points[unresolved],maximum+distance)
  point_ids=np.repeat(unresolved,[len(x) for x in neighborhoods]);triangle_ids=np.array([i for values in neighborhoods for i in values],dtype=int)
  if not len(triangle_ids):continue
  possible=np.linalg.norm(points[point_ids]-centers[triangle_ids],axis=1)<=radii[triangle_ids]+distance
  point_ids=point_ids[possible];triangle_ids=triangle_ids[possible]
  good=point_triangle_distance_squared(points[point_ids],triangles[triangle_ids])<=distance**2
  valid[point_ids[good]]=True
 return bool(valid.all())

def sample_batches(triangles,diameter,budget=10_000_000):
 # Recursively split each triangle until its diameter is bounded. Its centroid
 # is within that diameter of every point on the triangle. Combined with the
 # distance check this supplies a stated surface tolerance, not just vertices.
 batch=[];count=0
 for triangle in triangles:
  pending=[triangle]
  while pending:
   a,b,c=pending.pop();lengths=[np.linalg.norm(b-a),np.linalg.norm(c-b),np.linalg.norm(a-c)]
   if max(lengths)>diameter:
    longest=int(np.argmax(lengths))
    if longest==0:m=(a+b)/2;pending.extend([np.array([a,m,c]),np.array([m,b,c])])
    elif longest==1:m=(b+c)/2;pending.extend([np.array([b,m,a]),np.array([m,c,a])])
    else:m=(c+a)/2;pending.extend([np.array([c,m,b]),np.array([m,a,b])])
   else:
    batch.append((a+b+c)/3);count+=1
    if count>budget:raise RuntimeError('Mesh surface comparison exceeds its declared sample budget')
    if len(batch)==2048:yield np.asarray(batch);batch=[]
 if batch:yield np.asarray(batch)

def compare(candidate,reference,tolerance=.10):
 a,area_a=arrays(candidate);b,area_b=arrays(reference)
 if abs(area_a-area_b)>max(.01,.01*area_b):return False
 for source,target in [(a,b),(b,a)]:
  lookup=index(target,tolerance)
  for points in sample_batches(source,tolerance/2):
   if not covered(points,lookup,tolerance/2):return False
 return True
