"""Deployment configuration and read-only resource checks for a dedicated VM."""
import hashlib,json,math,shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

@dataclass(frozen=True)
class Runtime:
    root: Path
    sdk: Path
    vmx: Path
    vmrun: str
    snapshot: str
    guest_apps: str
    guest_se: str
    controller_port: int
    guest_gib: float
    host_reserve_gib: float
    minimum_disk_free_gib: float
    config_sha256: str
    guest_controller_dir: str = '/home/user/server'
    provider: str = 'vmware'
    qemu: dict | None = None

    @property
    def lock(self): return self.root/'.vm_control.lock'

    @property
    def pending(self): return self.root/'validation/pending_guest_action.json'

    def has_pending(self,work_root):
        return self.pending.exists() or (Path(work_root)/'validation/pending_guest_action.json').exists()

    @classmethod
    def load(cls,path,*,validate=True):
        path=Path(path).resolve();data=json.loads(path.read_text(encoding='utf-8'))
        def local(name):
            value=Path(data[name]).expanduser()
            return (path.parent/value).resolve() if not value.is_absolute() else value.resolve()
        provider=data.get('provider','vmware')
        if provider not in {'vmware','qemu'}:raise ValueError('Unsupported COPASI provider')
        binary=data.get('vmrun_path') or shutil.which('vmrun') or shutil.which('vmrun.exe')
        if provider=='vmware' and not binary:raise ValueError('Set vmrun_path in runtime config or add vmrun to PATH')
        if data.get('vmrun_path'):
            value=Path(binary).expanduser();binary=str((path.parent/value).resolve() if not value.is_absolute() else value.resolve())
        policy=data.get('resources',{})
        obj=cls(local('runtime_root'),local('sdk_path'),local('vmx_path') if provider=='vmware' else local('image_path'),str(binary or ''),
            data.get('snapshot','copasi_bench_init'),data.get('guest_apps','/home/user/copasi_bench/apps'),
            data.get('guest_se','/home/user/copasi_bench/apps/CopasiSE-4.47.309'),
            int(data.get('controller_port',5001)),float(policy.get('guest_gib',4)),
            float(policy.get('host_reserve_gib',1)),float(policy.get('minimum_disk_free_gib',26)),
            hashlib.sha256(path.read_bytes()).hexdigest(),data.get('guest_controller_dir','/home/user/server'),provider,data.get('qemu'))
        if (not all(math.isfinite(v) for v in (obj.guest_gib,obj.host_reserve_gib,obj.minimum_disk_free_gib))
                or obj.guest_gib!=4 or obj.host_reserve_gib<1 or obj.minimum_disk_free_gib<26):
            raise ValueError('Engineering policy requires 4 GiB guest, >=1 GiB host reserve and >=26 GiB disk reserve')
        if not 1<=obj.controller_port<=65535:raise ValueError('Invalid controller port')
        if not obj.snapshot or not PurePosixPath(obj.guest_apps).is_absolute() or not PurePosixPath(obj.guest_se).is_absolute():
            raise ValueError('Require snapshot and absolute guest application paths')
        if not PurePosixPath(obj.guest_controller_dir).is_absolute():raise ValueError('Require absolute guest controller deployment path')
        if validate:
            if not obj.root.is_dir() or not obj.vmx.is_file() or (provider=='vmware' and not Path(obj.vmrun).is_file()):raise ValueError('Runtime root or VM assets not found')
            if provider=='qemu' and (not isinstance(obj.qemu,dict) or obj.qemu.get('accelerator','tcg') not in {'tcg','kvm'}):raise ValueError('Invalid QEMU configuration')
            manifest=json.loads((Path(__file__).parent/'sdk/manifest.json').read_text())
            for row in manifest['modified_files']:
                target=obj.sdk/row['path']
                if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest()!=row['patched_sha256']:
                    raise ValueError('Controller SDK compatibility patch missing or changed: '+row['path'])
        return obj

    def inspect_resources(self):
        import psutil
        gib=1024**3
        available=psutil.virtual_memory().available/gib
        root_free=shutil.disk_usage(self.root).free/gib
        vm_free=shutil.disk_usage(self.vmx.parent).free/gib
        free=min(root_free,vm_free)
        return {'available_gib':available,'required_available_gib':self.guest_gib+self.host_reserve_gib,
            'disk_free_gib':free,'runtime_disk_free_gib':root_free,'vm_disk_free_gib':vm_free,
            'conservative_additional_disk_gib':self.minimum_disk_free_gib,
            'memory_gate_pass':available>=self.guest_gib+self.host_reserve_gib,
            'disk_gate_pass':free>=self.minimum_disk_free_gib,'runtime_config_sha256':self.config_sha256}
