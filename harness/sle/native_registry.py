"""Native Harbor runtime identities; profiles never contain credential values."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Runtime:
    name: str
    native_class: str
    adapter: str
    binary: str
    npm_package: str
    key_env: str
    base_url_env: str
    protocol: str
    output_file: str


RUNTIMES = {
    'codex': Runtime('codex', 'harbor.agents.installed.codex.Codex',
        'sle.native_runtimes:CodexRuntime', 'codex', '@openai/codex',
        'OPENAI_API_KEY', 'OPENAI_BASE_URL', 'openai-responses', 'codex.txt'),
    'gemini-cli': Runtime('gemini-cli', 'harbor.agents.installed.gemini_cli.GeminiCli',
        'sle.native_runtimes:GeminiRuntime', 'gemini', '@google/gemini-cli',
        'GEMINI_API_KEY', 'GOOGLE_GEMINI_BASE_URL', 'gemini', 'gemini-cli.txt'),
    'qwen-code': Runtime('qwen-code', 'harbor.agents.installed.qwen_code.QwenCode',
        'sle.native_runtimes:QwenRuntime', 'qwen', '@qwen-code/qwen-code',
        'OPENAI_API_KEY', 'OPENAI_BASE_URL', 'openai-chat', 'qwen-code.txt'),
    'kimi-code': Runtime('kimi-code', 'harbor.agents.installed.kimi_code.KimiCode',
        'sle.native_runtimes:KimiRuntime', 'kimi', '@moonshot-ai/kimi-code',
        'KIMI_MODEL_API_KEY', 'KIMI_MODEL_BASE_URL', 'kimi', 'kimi-code.txt'),
    'mcode': Runtime('mcode', 'harbor.agents.installed.mcode.MCode',
        'sle.native_runtimes:MiniMaxRuntime', 'mcode', '@minimax-ai/code',
        'MINIMAX_API_KEY', 'MINIMAX_BASE_URL', 'anthropic', 'mcode.jsonl'),
}
ALIASES = {
    'codex-cli': 'codex', 'codexcli': 'codex',
    'gemini': 'gemini-cli', 'geminicli': 'gemini-cli',
    'qwen': 'qwen-code', 'qwencode': 'qwen-code',
    'kimicodecli': 'kimi-code', 'kimi-code-cli': 'kimi-code', 'kimicode': 'kimi-code',
    'minimaxcode': 'mcode', 'minimax-code': 'mcode', 'minimax': 'mcode',
}


def runtime(name):
    canonical = ALIASES.get(name.lower(), name.lower())
    if canonical not in RUNTIMES:
        raise ValueError('Unknown native runtime: ' + name)
    return RUNTIMES[canonical]


def native_model(spec, model):
    if not model:
        return model
    # Harbor's Gemini and MCode adapters require a provider prefix.
    if spec.name == 'gemini-cli' and '/' not in model:
        return 'google/' + model
    if spec.name == 'mcode' and '/' not in model:
        return 'minimax/' + model
    return model
