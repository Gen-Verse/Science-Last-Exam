"""Docker-native static networking for hosts that disallow privileged sidecars.

Only unchanged public or no-network policies are supported. Allowlists and
network transitions are rejected, never silently weakened.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import shlex
from urllib.parse import urlsplit

from harbor.environments.base import BaseEnvironment
from harbor.environments.capabilities import EnvironmentCapabilities
from harbor.environments.docker import docker as docker_module
from harbor.models.task.config import NetworkMode
from sle.docker_image_cache import CachedDockerBuildMixin, inspect_image


def prefer_local_pluto_source(text, resolver=inspect_image):
    """Replace only the download transport; retain the task's checksum check."""
    pin = re.search(r'^ARG PLUTO_SHA256=([a-f0-9]{64})$', text, re.MULTILINE)
    download = re.compile(r'^RUN curl -fsSLk "\$PLUTO_URL" -o /tmp/pluto\.tar\.gz', re.MULTILINE)
    if not pin or not download.search(text) or 'sha256sum -c -' not in text:
        return text, None
    reference = 'sle-source:pluto-' + pin[1]
    image = resolver(reference)
    if not image or (image.get('Config', {}).get('Labels') or {}).get('io.sle.source.sha256') != pin[1]:
        return text, None
    adapted = download.sub('COPY --from=' + reference + ' /source/pluto.tar.gz /tmp/pluto.tar.gz\nRUN true', text)
    return adapted, reference


def route_apt_through_mirror(text, mirror):
    # Some task Dockerfiles do not declare APT_MIRROR, so passing that build
    # argument alone leaves them downloading through the failing remote proxy.
    if re.search(r'^ARG APT_MIRROR(?:=|\s|$)', text, re.MULTILINE):
        return text
    replacement = mirror.rstrip('/').replace('\\', '\\\\').replace('&', '\\&').replace('|', '\\|')
    expression = shlex.quote('s|https\\?://deb.debian.org|' + replacement + '|g')
    prelude = ('for f in /etc/apt/sources.list /etc/apt/sources.list.d/*.list '
               '/etc/apt/sources.list.d/*.sources; do if [ -f "$f" ]; then '
               'sed -i ' + expression + ' "$f"; fi; done && ')
    return re.sub(r'^RUN\s+(?=apt-get\b)', lambda _: 'RUN ' + prelude, text, flags=re.MULTILINE)


def normalize_stage_owners(text):
    sources = {}
    for line in text.splitlines():
        if not line.startswith('COPY ') or '--from=' not in line:
            continue
        words = shlex.split(line)
        stage = next(word.split('=',1)[1] for word in words if word.startswith('--from='))
        paths = [word for word in words[1:] if not word.startswith('--')][:-1]
        sources.setdefault(stage, set()).update(paths)
    result=[];stage=None;index=-1
    for line in text.splitlines():
        if line.startswith('FROM '):
            owned=sources.get(stage,set()) | sources.get(str(index),set())
            if owned:
                result.append('RUN chown -R 0:0 -- '+shlex.join(sorted(owned)))
            index+=1
            match=re.search(r'\sAS\s+(\S+)',line,re.IGNORECASE)
            stage=match.group(1) if match else None
        result.append(line)
    return '\n'.join(result)+'\n'


class StaticNetworkDockerEnvironment(CachedDockerBuildMixin, docker_module.DockerEnvironment):
    @staticmethod
    def _requires_egress_control(**kwargs):
        return False

    @property
    def capabilities(self):
        return EnvironmentCapabilities(
            disable_internet=True, mounted=True, docker_compose=True,
        )

    def validate_network_policy_support(self, network_policy=None):
        policy = network_policy or self.network_policy
        BaseEnvironment.validate_network_policy_support(self, policy)
        if policy.network_mode != self.network_policy.network_mode:
            raise ValueError('Static Docker networking cannot change between phases')

    @property
    def _docker_compose_paths(self):
        paths = super()._docker_compose_paths
        if self.network_policy.network_mode == NetworkMode.NO_NETWORK:
            paths.append(Path(docker_module.__file__).with_name('docker-compose-no-network.yaml'))
        # LAPS sources/decks remain under /app and graded deliverables under
        # /logs/artifacts. Its disposable /work can otherwise fill Docker's root
        # layer with 3-D solver frames. Apply independently to solver and grader.
        if os.environ.get('SLE_LAPS_MEMORY_SCRATCH') == '1' and self.environment_dir.parent.name in {
            'laps-repair-multi2-2d-coef-mhd-l404k0-sign-mhdrhs-l80c64',
            'laps-repair-multi2-3d-coef-mhd-l433k0-sign-mhdrhs-l227c73',
        }:
            directory = self.trial_paths.trial_dir / 'environment-build' / self.session_id
            directory.mkdir(parents=True, exist_ok=True)
            override = directory / 'memory-scratch.json'
            override.write_text(json.dumps({'services': {'main': {
                'tmpfs': ['/work:rw,size=68719476736,mode=1777']}}}, indent=2)+'\n')
            paths.append(override)
        if os.environ.get('SLE_DOCKER_COPY_ROOT') == '1':
            directory = self.trial_paths.trial_dir / 'environment-build' / self.session_id
            directory.mkdir(parents=True, exist_ok=True)
            original = (self.environment_dir/'Dockerfile').read_text()
            # Archive ownership can exceed a user-namespaced daemon's UID map.
            # Normalize before COPY archives the source and maps its numeric IDs.
            adapted = normalize_stage_owners(original)
            adapted, local_source_image = prefer_local_pluto_source(adapted)
            apt_mirror=os.environ.get('SLE_DOCKER_APT_MIRROR','')
            if apt_mirror:
                address=urlsplit(apt_mirror)
                if address.scheme not in {'http','https'} or not address.hostname or address.username or address.password or address.query or address.fragment or address.path not in {'','/'}:
                    raise ValueError('Docker build mirror must be an origin URL without credentials or path')
                options='-o Acquire::Retries=3 -o Acquire::http::Timeout=180 -o Acquire::http::Pipeline-Depth=0'
                if address.hostname in {'172.17.0.1','127.0.0.1','localhost'}:
                    options+=' -o Acquire::http::Proxy::'+address.hostname+'=DIRECT'
                adapted=re.sub(r'\bapt-get\s+(update|install)\b',lambda match:'apt-get '+options+' '+match.group(1),adapted)
                adapted=route_apt_through_mirror(adapted, apt_mirror)
            dockerfile = directory/'Dockerfile'
            dockerfile.write_text(adapted)
            args = {}
            if os.environ.get('SLE_DOCKER_BUILD_PROXY'):
                args = {key:os.environ['SLE_DOCKER_BUILD_PROXY'] for key in ('http_proxy','https_proxy')}
            if apt_mirror:args['APT_MIRROR']=apt_mirror.rstrip('/')
            override = directory/'compose.json'
            override.write_text(json.dumps({'services':{'main':{'build':{
                'dockerfile':str(dockerfile),'args':args}}}}))
            (directory/'receipt.json').write_text(json.dumps({
                'source_dockerfile':str(self.environment_dir/'Dockerfile'),
                'source_sha256':hashlib.sha256(original.encode()).hexdigest(),
                'runtime_sha256':hashlib.sha256(adapted.encode()).hexdigest(),
                'build_apt_mirror':apt_mirror or None,
                'local_source_image':local_source_image,
                'adaptation':'Normalize stage ownership; use configured apt mirror and checksum-pinned local source image when available; task source unchanged.'},indent=2)+'\n')
            paths.append(override)
        return self._cache_compose_paths(paths)
