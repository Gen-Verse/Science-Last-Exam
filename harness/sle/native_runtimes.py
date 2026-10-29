"""Provider-specific configuration around Harbor's installed native runtimes.

Model invocation, sessions and trajectory conversion stay in Harbor's classes.
The GUI mixin supplies only lifecycle, tool restrictions and the finish receipt.
"""
from copy import deepcopy
import json
from pathlib import Path
import shlex

from harbor.agents.installed.codex import Codex
from harbor.agents.installed.gemini_cli import GeminiCli
from harbor.agents.installed.qwen_code import QwenCode
from harbor.agents.installed.kimi_code import KimiCode
from harbor.agents.installed.mcode import MCode
from sle.native_lifecycle import NativeLifecycle, read_events


# Canonical tool names from Qwen Code 0.26.0. MCP names remain task-scoped.
QWEN_BUILTINS = (
    'exec read_file zoom_image write_file edit notebook_edit glob grep_search '
    'run_shell_command list_directory read_mcp_resource web_fetch web_search image_gen '
    'todo_write save_memory manage_memory search_memory lsp cron_create cron_list '
    'cron_delete loop_wakeup create_sub_session monitor agent skill exit_plan_mode '
    'enter_plan_mode ask_user_question list_agents task_stop task_create task_update '
    'task_list team_create team_delete team_plan_approval request_shutdown send_message '
    'structured_output tool_call tool_search advisor enter_worktree exit_worktree workflow '
    'artifact record_artifact record_source report_findings get_goal update_goal propose_goal '
    'omni_downsample_image omni_downscale_video omni_downsample_audio omni_extract_keyframes '
    'omni_extract_audio omni_clip_video omni_convert_image omni_transcribe_audio '
    'omni_clip_image omni_clip_audio omni_caption_image omni_caption_audio omni_ocr_image '
    'omni_understand_video_segments omni_recall_media_memory display_image'
).split()


class CodexRuntime(NativeLifecycle, Codex):
    runtime_name = 'codex'

    async def prepare_runtime(self, environment):
        if self.mode != 'gui':
            return
        # Codex's apply_patch advertisement is a model capability, not just a
        # feature flag. Keep native model instructions while removing that capability.
        source = Path(self.codex_model_catalog or '~/.codex/models_cache.json').expanduser()
        if not source.is_file():
            raise ValueError('Codex GUI requires codex_model_catalog (native models_cache.json or models.json)')
        catalog = json.loads(source.read_text())
        models = catalog['models'] if isinstance(catalog, dict) else catalog
        model = self.model_name.split('/')[-1]
        template = self.codex_model_template or model
        selected = next((m for m in models if m['slug'] == template), None)
        if selected is None:
            raise ValueError('Model absent from Codex catalog; set codex_model_template explicitly')
        entry = deepcopy(selected)
        entry.update(slug=model, shell_type='disabled', apply_patch_tool_type=None,
                     experimental_supported_tools=[], supports_search_tool=False)
        self._gui_catalog_path = '/tmp/sle-codex-models.json'
        await self.upload_text(environment, self._gui_catalog_path, json.dumps({'models': [entry]}))

    def _build_effective_config(self, openai_base_url=None):
        config = super()._build_effective_config(openai_base_url)
        if self.mode == 'gui':
            # Fresh CODEX_HOME and explicit MCP list prevent ambient server discovery.
            config['mcp_servers'] = {'science_gui': config['mcp_servers']['science_gui']}
            config['model_catalog_json'] = self._gui_catalog_path
            config['web_search'] = 'disabled'
            features = config.setdefault('features', {})
            for name in ('shell_tool', 'unified_exec', 'apply_patch_freeform', 'view_image',
                         'image_generation', 'computer_use', 'multi_agent', 'collab',
                         'collaboration_modes', 'default_mode_request_user_input', 'js_repl',
                         'code_mode', 'connectors', 'plugins', 'memory_tool', 'skill_search',
                         'tool_search', 'search_tool', 'request_permissions', 'request_permissions_tool'):
                features[name] = False
            config['tools'] = {'update_plan': {'enabled': False},
                               'experimental_request_user_input': {'enabled': False}}
        return config

    def model_command(self, command):
        if self.mode == 'gui':
            # Harbor enables this flag explicitly in its native command.
            command = command.replace('--enable unified_exec ', '--disable unified_exec ', 1)
        return command

    def check_native_result(self, bounded):
        super().check_native_result(bounded)
        events = read_events(Path(self.logs_dir) / self.runtime.output_file)
        if not any(e.get('type') == 'turn.completed' for e in events):
            raise RuntimeError('Codex has no completed native turn')
        if self.mode == 'gui':
            for event in events:
                item = event.get('item') or {}
                if item.get('type') in {'command_execution', 'file_change', 'web_search', 'collab_tool_call'}:
                    raise RuntimeError('Codex GUI trace contains a non-GUI tool')
                if item.get('type') == 'mcp_tool_call' and item.get('server') != 'science_gui':
                    raise RuntimeError('Codex GUI trace used another MCP server')


class GeminiRuntime(NativeLifecycle, GeminiCli):
    runtime_name = 'gemini-cli'

    def _build_settings_config(self, model=None, auth_type=None):
        config, alias = super()._build_settings_config(model, auth_type)
        config = config or {}
        config.setdefault('model', {})['maxSessionTurns'] = self.max_steps
        if self.mode == 'gui':
            # A nonempty unmatched allowlist selects no built-in tools. An empty
            # array has differed in meaning across Gemini/Qwen versions.
            config['tools'] = {'core': ['sle_no_builtin_tool']}
            config['mcp'] = {'allowed': ['science_gui']}
            config['useWriteTodos'] = False
            config['experimental'] = {'skills': False, 'enableAgents': False}
            config['mcpServers']['science_gui']['trust'] = True
        return config, alias

    def check_native_result(self, bounded):
        super().check_native_result(bounded)
        candidates = [Path(self.logs_dir) / 'gemini-cli.trajectory.json',
                      Path(self.logs_dir) / 'gemini-cli.trajectory.jsonl']
        if not any(p.is_file() and p.stat().st_size for p in candidates):
            raise RuntimeError('Gemini CLI did not produce a native session trace')


class QwenRuntime(NativeLifecycle, QwenCode):
    runtime_name = 'qwen-code'

    def _build_register_mcp_servers_command(self):
        config = {'model': {'maxSessionTurns': self.max_steps}}
        if self.mcp_servers:
            config['mcpServers'] = {s.name: {'command': s.command, 'args': list(s.args),
                'trust': True} for s in self.mcp_servers}
        if self.mode == 'gui':
            config.update(tools={'core': ['sle_no_builtin_tool'], 'exclude': QWEN_BUILTINS,
                                 'disabled': QWEN_BUILTINS},
                          permissions={'deny': QWEN_BUILTINS}, mcp={'allowed': ['science_gui']})
        # Use $HOME inside the native container, never expand the host's home.
        return ('mkdir -p "$HOME/.qwen" && printf %s ' + shlex.quote(json.dumps(config))
                + ' > "$HOME/.qwen/settings.json"')

    def check_native_result(self, bounded):
        super().check_native_result(bounded)
        if self._find_session_jsonl() is None:
            raise RuntimeError('Qwen Code did not produce a native session trace')


class KimiRuntime(NativeLifecycle, KimiCode):
    runtime_name = 'kimi-code'

    def _runtime_env(self):
        return {**super()._runtime_env(), **self.runtime_env(),
            'KIMI_LOOP_MAX_STEPS_PER_TURN': str(self.max_steps),
            'KIMI_CODE_BUILTIN_PRODUCT_SKILLS': 'false'}

    async def prepare_runtime(self, environment):
        import toml
        config = {'default_permission_mode': 'yolo',
                  'loop_control': {'max_steps_per_turn': self.max_steps}}
        if self.mode == 'gui':
            config.update(tools={'enabled': ['mcp__science_gui__*']}, builtin_product_skills=False,
                permission={'rules': [{'pattern': 'mcp__science_gui__*', 'decision': 'allow'}]})
        path = '/logs/agent/.kimi-code/config.toml'
        await self.exec_as_agent(environment, command='mkdir -p /logs/agent/.kimi-code')
        await self.upload_text(environment, path, toml.dumps(config))

    def check_native_result(self, bounded):
        super().check_native_result(bounded)
        events = read_events(Path(self.logs_dir) / self.runtime.output_file)
        if not events:
            raise RuntimeError('Kimi Code did not produce native stream events')


class MiniMaxRuntime(NativeLifecycle, MCode):
    runtime_name = 'mcode'

    def build_cli_flags(self):
        # Native Harbor exposes max_steps; don't consume it only in our lifecycle.
        flags = super().build_cli_flags()
        if '--max-steps' not in flags:
            flags += ' --max-steps ' + str(self.max_steps)
        return flags.strip()

    def _build_register_mcp_servers_command(self):
        native = super()._build_register_mcp_servers_command()
        if self.mode != 'gui':
            return native
        # This hook runs AFTER Harbor has written its provider/runtime YAML.
        # Merge, instead of appending a second `agents` key to the YAML document.
        path = self._DATA_DIR + '/' + self._RUNTIME_CONFIG_FILENAME
        patch = (
            'import pathlib,yaml; '
            f'p=pathlib.Path({path!r}); d=yaml.safe_load(p.read_text()); '
            "d['agents']={'default':{'tools':[],'builtinTools':[],'skills':[],"
            "'features':{'mavis':False,'delegation':False,'webSearch':False}}}; "
            'p.write_text(yaml.safe_dump(d,sort_keys=False))'
        )
        return (native or 'true') + ' && python -c ' + shlex.quote(patch)

    def check_native_result(self, bounded):
        super().check_native_result(bounded)
        events = read_events(Path(self.logs_dir) / self.runtime.output_file)
        terminal = next((e for e in reversed(events) if e.get('type') in {'result', 'exec.result', 'exec.completed'}), None)
        if not terminal:
            raise RuntimeError('MiniMax Code has no terminal native result')
        status = terminal.get('status') or (terminal.get('result') or {}).get('status')
        if status not in {'success', 'succeeded', 'completed', 'done', 'ok'}:
            raise RuntimeError('MiniMax Code did not report successful completion')

    def populate_context_post_run(self, context):
        super().populate_context_post_run(context)
        events = read_events(Path(self.logs_dir) / self.runtime.output_file)
        terminal = next((e for e in reversed(events) if e.get('type') in {'exec.result', 'exec.completed'}), None)
        if not terminal:
            return
        result = terminal.get('result') or terminal
        usage = result.get('usage') or {}
        for source, target in [('inputTokens', 'n_input_tokens'), ('outputTokens', 'n_output_tokens'),
                               ('cacheReadTokens', 'n_cache_tokens')]:
            value = usage.get(source)
            if type(value) is int and value >= 0:
                setattr(context, target, value)
        context.metadata = {**(context.metadata or {}), 'native_usage': usage,
            'usage_source': result.get('usageSource'), 'usage_complete': not result.get('usageIncomplete', False)}
