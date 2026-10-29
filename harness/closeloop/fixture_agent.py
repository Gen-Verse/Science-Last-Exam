"""Development artifact-transfer fixture. No model, no research-success oracle."""
from pathlib import Path
from harbor.agents.base import BaseAgent
from harbor.agents.options import AgentOptions

class Options(AgentOptions):
    fixture_dir: str

class FixtureAgent(BaseAgent):
    options_model=Options
    @staticmethod
    def name():return 'sle-development-fixture'
    def version(self):return '0.1.0'
    async def setup(self,environment):
        from harbor_agent import HostedCodexAgent
        await HostedCodexAgent.setup(self,environment)
    async def run(self,instruction,environment,context):
        await environment.upload_dir(Path(self.options.fixture_dir),'/workspace')
        result=await environment.exec('test -s /workspace/output/submission.json && test -d /workspace/state/runs && ls /workspace/output && ls /workspace/state/runs',timeout_sec=30)
        self.logs_dir.mkdir(parents=True,exist_ok=True)
        (self.logs_dir/'fixture.log').write_text((result.stdout or '')+(result.stderr or ''))
        if result.return_code or not result.stdout:
            raise RuntimeError('Fixture artifact transfer or command output failed.')
        context.metadata={'development_fixture':True,'model_dispatched':False,'source':str(Path(self.options.fixture_dir).resolve()),'purpose':'Science's Last Exam migration artifact-transfer and independent replay check'}
