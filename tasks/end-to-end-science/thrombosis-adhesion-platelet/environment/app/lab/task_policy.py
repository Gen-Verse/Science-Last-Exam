"""Frozen v0 scope; no experimental design or optimizer is embedded here."""
from .models import Experiment

VERSION = "0.1.1"
MAX_RUNS = 6
FIXED = dict(model="clotfoam_sd2026", template="channel3D_shear300", boundary="flow",
    pressure_drop=None, duration_s=0.05, write_interval_s=0.025, max_dt_s=0.001,
    max_co=0.5, reaction_substeps=2, cores=4, wall_seconds=300, coagulation=True,
    no_injury=False, tissue_factor_multiplier=1.0, length_multiplier=1.0,
    height_multiplier=1.0, injury_multiplier=1.0, flow_multiplier=1.0,
    mesh_refinement=1, initial_conditions="published")
ANNOTATIONS = {"hypothesis", "predicted_observation", "rationale", "parent_run", "role"}

def validate(spec):
    unknown=set(spec)-set(Experiment.model_fields)
    if unknown:
        raise ValueError("Unknown fields: "+str(sorted(unknown)))
    for k,v in FIXED.items():
        if k in spec and (type(spec[k]) is not type(v) and isinstance(v,bool) or spec[k]!=v):
            raise ValueError(f"v0 fixes {k}={v!r}; unsupported condition")
    c=Experiment(**{**FIXED, **spec}).model_dump()
    for k in ["adhesion_multiplier", "platelet_multiplier"]:
        if isinstance(spec.get(k),bool): raise ValueError("A multiplier must be numeric")
    return c

def matched(a,b):
    a,b=validate(a),validate(b)
    differences={k:[a[k],b[k]] for k in a if k not in ANNOTATIONS|{"adhesion_multiplier"} and a[k]!=b[k]}
    if differences: raise ValueError("Unmatched controls: "+str(differences))
    if not a["adhesion_multiplier"]>b["adhesion_multiplier"]:
        raise ValueError("control adhesion must be greater than intervention adhesion")
    return True
