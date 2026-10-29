"""Trusted template adapters. No reduced-order or fabricated solver fallback."""
import hashlib,json,os,re,resource,shutil,signal,subprocess,time
from pathlib import Path
from . import store
from .models import Experiment
ROOT=store.ROOT
SERVICE_CODE_HASH=hashlib.sha256(b''.join(p.read_bytes() for p in sorted((ROOT/'lab').glob('*.py')))).hexdigest()
VENDOR={'clotfoam2023':('clotFoam','clotFoam'),'clotfoam_sd2026':('clotFoam_sd','clotFoam_sD')}

class Cancelled(Exception): pass
class BudgetTimeout(Exception): pass

def replace_entry(text,key,value):
    pattern=rf'(?m)^(\s*{re.escape(key)}\s+)[^;\n]+;'
    if not re.search(pattern,text): return text+f'\n{key} {value};\n'
    return re.sub(pattern,lambda m:m.group(1)+str(value)+';',text,count=1)

def number(text,key):
    m=re.search(rf'(?m)^\s*{re.escape(key)}\s+([-+\d.eE]+)\s*;',text)
    if not m:raise ValueError(f'No numeric parameter {key}')
    return float(m.group(1))

def patch_boundary(text,patch,body):
    m=re.search(rf'\b{re.escape(patch)}\s*\{{',text)
    if not m:raise ValueError(f'Missing boundary {patch}')
    pos=m.end(); depth=1
    while depth:
        if pos>=len(text):raise ValueError('Malformed boundary')
        if text[pos]=='{':depth+=1
        elif text[pos]=='}':depth-=1
        pos+=1
    return text[:m.start()]+patch+'\n{\n'+body+'\n}'+text[pos:]

def prepare(directory:Path,spec:dict):
    c=Experiment(**spec); repo,solver=VENDOR[c.model]
    src=ROOT/'vendor'/repo/'tutorials'/c.template
    if not src.is_dir(): raise RuntimeError('Pinned upstream source is not provisioned')
    shutil.copytree(src,directory,ignore=shutil.ignore_patterns('._*'))
    params=directory/'constant/inputParameters'; text=params.read_text()
    changes={}
    multipliers={'Plt_0':c.platelet_multiplier,'E0_IC':c.tissue_factor_multiplier}
    if c.template=='bleedingChip3D':multipliers.update(Q_left=c.flow_multiplier,Q_right=c.flow_multiplier)
    else:
        multipliers.update(inletShearRate=c.flow_multiplier,x_max=c.length_multiplier,y_max=c.height_multiplier,w_inj=c.injury_multiplier)
        if c.model=='clotfoam_sd2026':multipliers['l_inj']=c.injury_multiplier
    if c.model=='clotfoam_sd2026':
        if c.template!='bleedingChip3D':multipliers['inletFlowRate']=c.flow_multiplier
        multipliers.update(kAdhCol=c.adhesion_multiplier,kAdhVwfOn300=c.adhesion_multiplier,kAdhVwfOn1500=c.adhesion_multiplier)
    else:multipliers['kAdh']=c.adhesion_multiplier
    for key,mult in multipliers.items():
        val=number(text,key)*mult
        if c.no_injury and key in ['kAdh','kAdhCol','kAdhVwfOn300','kAdhVwfOn1500','E0_IC']:val=0
        changes[key]=val; text=replace_entry(text,key,f'{val:.12g}')
    text=replace_entry(text,'M_rxn',c.reaction_substeps)
    if c.mesh_refinement==2:
        for key in (['Nx','Ny'] if c.model=='clotfoam2023' else ['NxMid','NyMid','NzMid','NxLegs','NyLegs'] if c.template=='bleedingChip3D' else ['Nx_up','Nx_down','Ny','Nz']):
            text=replace_entry(text,key,int(number(text,key)*2))
        if c.model=='clotfoam_sd2026' and c.template!='bleedingChip3D':text=replace_entry(text,'ds',number(text,'ds')/2)
    params.write_text(text)
    if c.initial_conditions=='rest' and c.model=='clotfoam_sd2026':
        for name,value in [('U','(0 0 0)'),('p','0')]:
            p=directory/'0'/name
            p.write_text(re.sub(r'#include\s+"'+name+r'_IC.dat"',f'internalField uniform {value};',p.read_text()))
    if c.boundary=='pressure':
        p=directory/'0/p'; p.write_text(patch_boundary(p.read_text(),'inletVessel',f'type fixedValue; value uniform {c.pressure_drop};'))
        p=directory/'0/U'; p.write_text(patch_boundary(p.read_text(),'inletVessel','type pressureInletOutletVelocity; value uniform (0 0 0);'))
    if c.no_injury:
        p=directory/'0/Hadh'; text=p.read_text(); start=text.index('internalField'); end=text.index('boundaryField',start)
        p.write_text(text[:start]+'internalField uniform 0;\n\n'+text[end:])
    p=directory/'system/controlDict';text=p.read_text()
    # Replace functions only: generated callbacks are trusted, never supplied by the agent.
    text=re.split(r'\nfunctions\s*\{',text,maxsplit=1)[0]
    for key,val in {'stopAt':'endTime','endTime':c.duration_s,'writeControl':'adjustableRunTime','writeInterval':c.write_interval_s,'writeCompression':'off','writePrecision':10,'timePrecision':10,'maxDeltaT':c.max_dt_s,'maxCo':c.max_co,'runTimeModifiable':'false'}.items():text=replace_entry(text,key,val)
    if c.model=='clotfoam_sd2026':text=replace_entry(text,'coagReactionsOn','true' if c.coagulation else 'false')
    # Persist ADP history to permit future scientifically exact checkpointing.
    hist=' '.join(['tau']+[f'ddt_Pbnew_{i}' for i in range(25)])
    funcs='\nfunctions\n{\n'
    funcs+=f'history {{ type writeObjects; libs ("libutilityFunctionObjects.so"); objects ({hist}); writeOption anyWrite; writeControl writeTime; writeInterval 1; }}\n'
    for name,op in [('plateletVolume','volIntegrate'),('plateletMean','volAverage')]:
        funcs+=f'{name} {{ type volFieldValue; libs ("libfieldFunctionObjects.so"); writeControl writeTime; writeInterval 1; writeFields false; operation {op}; fields (Theta_B Theta_T); }}\n'
    ports=[('inletFlux','inletVessel','sum','phi'),('outletFlux','outletVessel','sum','phi'),('inletPressure','inletVessel','areaAverage','p'),('outletPressure','outletVessel','areaAverage','p')]
    if c.template=='bleedingChip3D':ports=[(port+'Flux',port,'sum','phi') for port in ['inletLeft','inletRight','outletLeft','outletRight']]
    for name,patch,op,field in ports:
        funcs+=f'{name} {{ type surfaceFieldValue; libs ("libfieldFunctionObjects.so"); writeControl writeTime; writeInterval 1; writeFields false; regionType patch; name {patch}; operation {op}; fields ({field}); }}\n'
    p.write_text(text+funcs+'}\n')
    p=directory/'system/decomposeParDict';text=p.read_text();p.write_text(replace_entry(text,'numberOfSubdomains',c.cores))
    manifest={'service_code_sha256':SERVICE_CODE_HASH,'config':spec,'parameter_changes':changes,'upstream':json.loads((ROOT/'sources/manifest.json').read_text()),'units':{'length':'mm','time':'s','velocity':'mm/s','kinematic_pressure':'mm²/s²','volume':'mm³','source_data':'synthetic simulation, not patient data'},'files':{}}
    for p in sorted(directory.rglob('*')):
        if p.is_file():manifest['files'][str(p.relative_to(directory))]=hashlib.sha256(p.read_bytes()).hexdigest()
    (directory.parent/'provenance.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    return solver

def command(args,case,log,deadline,cancel_file):
    started=time.monotonic(); usage0=resource.getrusage(resource.RUSAGE_CHILDREN)
    with log.open('ab',buffering=0) as out:
        out.write(('\nCOMMAND '+json.dumps(args)+'\n').encode())
        prefix=['runuser','-u','nobody','--'] if hasattr(os,'geteuid') and os.geteuid()==0 else []
        process=subprocess.Popen([*prefix,'bash',str(ROOT/'scripts/run-foam.sh'),*args],cwd=case,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            while process.poll() is None:
                if cancel_file.exists():raise Cancelled('Experiment cancelled')
                if time.monotonic()>deadline:raise BudgetTimeout('Wall-clock budget exhausted')
                time.sleep(.3)
            if process.returncode:raise RuntimeError(f'{args[0]} exited with {process.returncode}; inspect solver log')
        except BaseException:
            if process.poll() is None:
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()
            raise
        finally:
            usage=resource.getrusage(resource.RUSAGE_CHILDREN)
            metrics={'command':args,'wall_seconds':time.monotonic()-started,
                'child_user_cpu_seconds':usage.ru_utime-usage0.ru_utime,
                'child_system_cpu_seconds':usage.ru_stime-usage0.ru_stime,
                'max_child_rss_kb':usage.ru_maxrss,'returncode':process.returncode}
            with (case.parent/'resources.jsonl').open('a') as f:f.write(json.dumps(metrics)+'\n')


def execute(r):
    started=time.monotonic(); root=store.STATE/'runs'/r['id'];root.mkdir(parents=True,exist_ok=True)
    case=root/'case'; c=Experiment(**r['config']);deadline=started+c.wall_seconds;log=root/'solver.log'; cancel=root/'cancel'
    try:
        solver=prepare(case,r['config'])
        if hasattr(os,'geteuid') and os.geteuid()==0:
            for p in [case,*case.rglob('*')]:
                if not p.is_symlink(): shutil.chown(p,user='nobody',group='nogroup')
        for args in [['blockMesh'],*([['topoSet'],['createPatch','-overwrite']] if c.model=='clotfoam_sd2026' else []),['checkMesh']]:
            store.update_run(r['id'],phase=args[0]);command(args,case,log,deadline,cancel)
        store.update_run(r['id'],phase='solving')
        if c.cores>1:
            command(['decomposePar','-force'],case,log,deadline,cancel)
            command(['mpirun','-np',str(c.cores),solver,'-parallel'],case,log,deadline,cancel)
            store.update_run(r['id'],phase='reconstructing'); command(['reconstructPar'],case,log,deadline,cancel)
        else:command([solver],case,log,deadline,cancel)
        from .analysis import numeric_times,build_summary
        times=numeric_times(case)
        if not times or times[-1][0]<c.duration_s*(1-1e-5):raise RuntimeError('Solver did not reach requested physical end time')
        store.update_run(r['id'],phase='postprocessing')
        for func in ['writeCellCentres','writeCellVolumes']:command(['postProcess','-func',func,'-time','0'],case,log,deadline,cancel)
        summary=build_summary(case,c)
        if not summary['numerical_checks']['finite_fields']:raise RuntimeError('Non-finite physical field values')
        (root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,allow_nan=False))
        store.update_run(r['id'],status='completed',phase='completed',summary=summary,elapsed_seconds=time.monotonic()-started,finished_at=store.now())
    except Exception as e:
        state='cancelled' if isinstance(e,Cancelled) else 'failed'
        kind='resource_exhausted' if isinstance(e,BudgetTimeout) else 'cancelled' if isinstance(e,Cancelled) else 'solver_or_pipeline_failure'
        store.update_run(r['id'],status=state,phase=state,error=str(e),failure_kind=kind,elapsed_seconds=time.monotonic()-started,finished_at=store.now())
