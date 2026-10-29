"""Create an installation disk or finalize a supplied, provisioned image.

Provisioning is explicit: no operating system, proprietary installer, or license
is downloaded implicitly. A disk copy is never claimed to be a validated VM.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("profile", choices=[x.name for x in Path(__file__).parent.iterdir() if (x / "image.json").exists()])
    p.add_argument("--output-dir", type=Path, required=True)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--base", type=Path, help="Powered-off, already provisioned base disk")
    source.add_argument("--install-iso", type=Path, help="Boot an OS installer; produces a pending installation disk")
    p.add_argument("--disk-size", default="80G")
    p.add_argument("--accelerator", choices=["kvm", "tcg"], default="kvm")
    args = p.parse_args(argv)
    spec = json.loads((Path(__file__).parent / args.profile / "image.json").read_text())
    binary = shutil.which("qemu-img")
    if not binary: p.error("qemu-img is required on the image build host")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    pending = args.output_dir / (args.profile + ".pending.qcow2")
    final = args.output_dir / spec["filename"]
    if pending.exists() or final.exists(): p.error("Output exists; use a new output directory")
    if args.base:
        if not args.base.is_file():p.error("Base disk does not exist")
        subprocess.run([binary, "convert", "-O", "qcow2", str(args.base), str(pending)], check=True)
        subprocess.run([binary, "check", str(pending)], check=True)
        pending.rename(final)
        print(json.dumps({"image":str(final),'runtime_verified':False,
            'next':'Boot the image, verify software versions, provision the bridge, and run an actual task'}))
    else:
        qemu = shutil.which("qemu-system-x86_64")
        if not qemu or not args.install_iso.is_file():p.error("QEMU and a local installation ISO are required")
        subprocess.run([binary,"create","-f","qcow2",str(pending),args.disk_size],check=True)
        print('Install the OS and applications, provision the bridge, then shut down. The disk remains pending.',flush=True)
        subprocess.run([qemu,'-accel',args.accelerator,'-m',str(spec['memory_mb']),'-smp',str(spec['cpus']),
            '-drive',f'file={pending},format=qcow2','-cdrom',str(args.install_iso),'-boot','d',
            '-vga','std','-netdev','user,id=n0','-device','e1000,netdev=n0'],check=True)
    return 0


if __name__ == '__main__':raise SystemExit(main())
