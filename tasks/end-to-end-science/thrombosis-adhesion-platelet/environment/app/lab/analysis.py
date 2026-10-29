import gzip,hashlib,json,re
from pathlib import Path
import numpy as np

def read_field(path:Path,n=None):
    if not path.exists() and path.with_suffix(path.suffix+'.gz').exists():path=path.with_suffix(path.suffix+'.gz')
    text=gzip.open(path,'rt').read() if path.suffix=='.gz' else path.read_text()
    text=re.sub(r'/\*.*?\*/|//[^\n]*','',text,flags=re.S)
    m=re.search(r'internalField\s+nonuniform\s+List<(scalar|vector)>\s+(\d+)\s*\((.*?)\)\s*;',text,re.S)
    if m:
        a=np.fromstring(m.group(3).replace('(',' ').replace(')',' '),sep=' ')
        count=int(m.group(2));width=3 if m.group(1)=='vector' else 1
        if len(a)!=count*width:raise ValueError(f'Incomplete field {path.name}')
        return a.reshape(count,3) if width==3 else a
    m=re.search(r'internalField\s+uniform\s+([^;]+);',text)
    if not m:raise ValueError(f'Unsupported field {path.name}')
    val=np.fromstring(m.group(1).replace('(',' ').replace(')',' '),sep=' ')
    if len(val)==1:return np.full(n or 1,val[0])
    if len(val)==3:return np.tile(val,(n or 1,1))
    raise ValueError('Invalid uniform field')

def numeric_times(case):
    result=[]
    for p in case.iterdir():
        try:t=float(p.name)
        except ValueError:continue
        if p.is_dir() and t>0:result.append((t,p))
    return sorted(result)

def series(case,name):
    result={}
    for p in sorted((case/'postProcessing'/name).glob('*/*.dat')):
        for line in p.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith('#'):
                try:
                    vals=[float(x) for x in line.replace('(',' ').replace(')',' ').split()]
                    result[vals[0]]=vals[1:]
                except ValueError:continue
    return result

def build_summary(case,c):
    volumes=read_field(case/'0/V');n=len(volumes)
    curves={name:series(case,name) for name in ['inletFlux','outletFlux','inletPressure','outletPressure']}
    if c.template=='bleedingChip3D':
        for kind in ['inlet','outlet']:
            left=series(case,kind+'LeftFlux');right=series(case,kind+'RightFlux')
            curves[kind+'Flux']={t:[v[0]+right[t][0]] for t,v in left.items() if t in right}
    timeline=[];min_theta=1.;max_theta=0.;finite=True
    for t,d in numeric_times(case):
        b=read_field(d/'Theta_B',n);total=read_field(d/'Theta_T',n)
        finite &= bool(np.isfinite(b).all() and np.isfinite(total).all())
        min_theta=min(min_theta,float(total.min()));max_theta=max(max_theta,float(total.max()))
        row={'time_s':t,'bound_platelet_volume_mm3':float(np.sum(b*volumes)),'mean_bound_fraction':float(np.average(b,weights=volumes)),'max_total_fraction':float(total.max())}
        for field in ['U','p','ADP','fluidPhase_S1','fluidPhase_S2','fluidPhase_E1','fluidPhase_E2','seBound_E0','seBound_C0','pltBound_S1b','pltBound_S2b','pltBound_E1b','pltBound_E2b','pltBound_C1','pltBound_C2']:
            if not (d/field).exists() and not (d/(field+'.gz')).exists():raise ValueError('Missing required solved field: '+field)
            a=read_field(d/field,n);finite &= bool(np.isfinite(a).all())
            if field in ['ADP','fluidPhase_E2']:
                name='adp' if field=='ADP' else 'thrombin'
                row[name+'_mean_nmol_mm3']=float(np.average(a,weights=volumes))
                row[name+'_max_nmol_mm3']=float(np.max(a))
        for name,values in curves.items():
            match=[k for k in values if abs(k-t)<max(1e-7,t*1e-7)]
            row[name]=values[match[0]][0] if match else None
        qin=row['inletFlux'];qout=row['outletFlux']
        row['flux_balance_relative']=abs(qin+qout)/max(abs(qin),abs(qout),1e-15) if qin is not None and qout is not None else None
        row['pressure_drop_mm2_s2']=row['inletPressure']-row['outletPressure'] if row['inletPressure'] is not None and row['outletPressure'] is not None else None
        timeline.append(row)
    residuals=[r['flux_balance_relative'] for r in timeline if r['flux_balance_relative'] is not None]
    checks={'finite_fields':finite,'min_total_platelet_fraction':min_theta,'max_total_platelet_fraction':max_theta,'max_flux_balance_relative':max(residuals) if residuals else None,'mesh_check_passed':'Mesh OK.' in (case.parent/'solver.log').read_text(errors='replace'),'convergence':'not_established_requires_matched_refinement_run'}
    return {'analysis_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'source':'real_clotFoam_simulation','data_type':'synthetic_model_output','dimension':2 if c.model=='clotfoam2023' else 3,'cells':n,'physical_end_s':timeline[-1]['time_s'],'timeline':timeline,'numerical_checks':checks,'endpoint':'right_censored_no_occlusion_claim_without_matched_baseline','boundary':c.boundary,'coagulation':c.coagulation,'units':{'length':'mm','volume':'mm³','flux':'mm³/s','kinematic_pressure':'mm²/s²'},'limitations':['Model-world result; not a clinical lipid threshold','Published microfluidic geometry, not patient arterial anatomy','Boundary conditions and coagulation switch must match when comparing runs']}

def frame(case:Path,time_s:float,max_points=6000):
    ts=numeric_times(case)
    if not ts:raise ValueError('No simulation frames yet')
    t,d=min(ts,key=lambda x:abs(x[0]-time_s))
    centers=read_field(case/'0/C');n=len(centers)
    theta=read_field(d/'Theta_B',n);u=read_field(d/'U',n)
    # Render a labelled central z-slice of true 3D data, never a synthetic clot animation.
    z=centers[:,2];levels=np.unique(z);zc=levels[np.argmin(abs(levels-(z.min()+z.max())/2))]
    ids=np.flatnonzero(np.isclose(z,zc,rtol=1e-6,atol=1e-10))
    ids=ids[::max(1,int(np.ceil(len(ids)/max_points)))]
    return {'time_s':t,'slice_z_mm':float(zc),'source':'solver_cell_fields','xyz_mm':centers[ids].round(9).tolist(),'bound_fraction':theta[ids].tolist(),'velocity_mm_s':u[ids].tolist(),'bounds_mm':[centers.min(axis=0).tolist(),centers.max(axis=0).tolist()]}

def compare(a,b):
    """No claims from unmatched simulations. Relative effect + numeric convergence only."""
    if a['status']!='completed' or b['status']!='completed':raise ValueError('Both runs must be completed')
    ca,cb=a['config'],b['config']
    if any(ca.get(k,1)!=cb.get(k,1) for k in ['model','template','boundary','duration_s','initial_conditions','length_multiplier','height_multiplier','injury_multiplier']):raise ValueError('Model, geometry, boundary and observation horizon must match')
    va=a['summary']['timeline'][-1]['bound_platelet_volume_mm3'];vb=b['summary']['timeline'][-1]['bound_platelet_volume_mm3']
    effect=(vb-va)/abs(va) if abs(va)>1e-18 else None
    result={'baseline':a['id'],'candidate':b['id'],'bound_volume_relative_change':effect,'changed_parameters':{k:[ca[k],cb[k]] for k in ca if ca[k]!=cb[k]},'claim':'model_world_comparison_not_clinical_efficacy','baseline_numerical_checks':a['summary']['numerical_checks'],'candidate_numerical_checks':b['summary']['numerical_checks']}
    if ca['boundary']=='pressure' and ca['no_injury'] and ca['pressure_drop']==cb['pressure_drop']:
        ta=a['summary']['timeline'];tb=b['summary']['timeline']; ratios=[]
        for row in tb:
            ref=min(ta,key=lambda x:abs(x['time_s']-row['time_s']))
            q0=ref.get('outletFlux');q=row.get('outletFlux')
            if q0 is not None and q is not None and abs(q0)>1e-15:ratios.append((row['time_s'],abs(q/q0)))
        onset=None;occluded=False
        for t,ratio in ratios:
            if ratio<=.1:
                if onset is None:onset=t
                if t-onset>=30:occluded=True;break
            else:onset=None
        result['occlusion_assessment']={'observed':occluded,'onset_s':onset if occluded else None,'definition':'Q/Q_no_injury <= 0.1 continuously over recorded samples for >=30s; model-specific operational rule','censored':not occluded,'sampling_interval_s':cb['write_interval_s']}
    else:result['occlusion_assessment']={'status':'not_assessed','reason':'Requires a matched no-injury baseline at the same fixed pressure; fixed-flow pressure rise is not flow occlusion'}
    return result
