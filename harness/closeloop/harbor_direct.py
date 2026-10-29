#!/usr/bin/env python3
"""Run the dedicated Harbor CLI with process-local direct network settings."""
import os
for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
    os.environ.pop(key, None)
os.environ.update(NO_PROXY='*', no_proxy='*')
import httpx
for cls in (httpx.Client, httpx.AsyncClient):
    original = cls.__init__
    def direct_init(self, *a, _original=original, **kw):
        kw['trust_env'] = False
        return _original(self, *a, **kw)
    cls.__init__ = direct_init
import requests
original_session_init = requests.Session.__init__
def direct_session_init(self, *args, **kwargs):
    original_session_init(self, *args, **kwargs)
    self.trust_env = False
requests.Session.__init__ = direct_session_init
os.environ['DOCKER_BUILDKIT']='0'
os.environ['LITELLM_LOCAL_MODEL_COST_MAP']='True'
from pathlib import Path
base=Path(__file__).resolve().parents[2]
os.environ['DOCKER_CONFIG']=str(base/'.local/closeloop/docker_client')
from harbor.environments.docker import docker as docker_module
from docker_runtime import OfflineDockerEnvironment
docker_module.DockerEnvironment=OfflineDockerEnvironment
from harbor.cli.main import app
app()
