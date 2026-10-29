"""Harbor launcher, model proxy retained only in the hosted policy process."""
import os,runpy,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import harbor_agent
harbor_agent.INFERENCE_PROXY_ENV={k:os.environ[k] for k in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy','NO_PROXY','no_proxy'] if k in os.environ}
if os.environ.get('SLE_CLOSELOOP_BACKEND', 'bridge') == 'bridge':
    runpy.run_path(str(Path(__file__).with_name('harbor_direct.py')),run_name='__main__')
else:
    runpy.run_module('harbor.cli.main', run_name='__main__')
