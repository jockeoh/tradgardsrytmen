"""ChatGPT-only CLI transport for structured garden research."""
import json
import os
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings


def environment():
    binary = Path(settings.RESEARCH_CODEX_BIN)
    env = {k: os.environ[k] for k in ('HOME', 'PATH', 'LANG') if k in os.environ}
    if settings.RESEARCH_CODEX_HOME:
        env['CODEX_HOME'] = settings.RESEARCH_CODEX_HOME
    env['PATH'] = str(binary.parent) + os.pathsep + env.get('PATH', os.defpath)
    return env


def check_login():
    login = subprocess.run([settings.RESEARCH_CODEX_BIN, 'login', 'status'], env=environment(),
                           capture_output=True, text=True, timeout=5)
    if login.returncode or 'Logged in using ChatGPT' not in (login.stdout + login.stderr).splitlines():
        raise ValueError('Codex CLI kräver ChatGPT-inloggning.')


def execute(body):
    tool = body['tools'][0]
    with tempfile.TemporaryDirectory(prefix='garden-research-') as tmp:
        schema = Path(tmp, 'schema.json')
        output = Path(tmp, 'result.json')
        schema.write_text(json.dumps(body['text']['format']['schema']))
        options = {'forced_login_method': 'chatgpt', 'web_search': 'live',
                   'model_reasoning_effort': 'low', 'tools.web_search.allowed_domains': tool['filters']['allowed_domains'],
                   'features.shell_tool': False, 'features.unified_exec': False, 'features.apps': False,
                   'features.plugins': False, 'features.multi_agent': False}
        for key in ('country', 'city', 'region'):
            options['tools.web_search.location.' + key] = tool['user_location'][key]
        cmd = [settings.RESEARCH_CODEX_BIN, 'exec', '--strict-config', '--ephemeral', '--ignore-rules',
               '--skip-git-repo-check', '--ignore-user-config', '--sandbox', 'read-only',
               '--model', body['model'], '--json', '--output-schema', str(schema), '--output-last-message', str(output)]
        for key, value in options.items():
            cmd.extend(['-c', f'{key}={json.dumps(value, ensure_ascii=False)}'])
        cmd.extend(['-c', 'mcp_servers={}', '-'])
        response = subprocess.run(cmd, input=body['input'], text=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, cwd=tmp, env=environment(), timeout=155, check=True)
        sources = {}
        for line in response.stdout.splitlines():
            event = json.loads(line)
            item = event.get('item', {})
            if event.get('type') == 'item.completed' and item.get('type') == 'web_search':
                for hit in item.get('results', []):
                    if hit.get('type') == 'text_result' and hit.get('url'):
                        sources[hit['url']] = {'url': hit['url'], 'title': hit.get('title')}
        return json.dumps({'output': [
            {'type': 'message', 'content': [{'type': 'output_text', 'text': output.read_text()}]},
            {'type': 'web_search_call', 'action': {'sources': list(sources.values())}},
        ]}).encode()
