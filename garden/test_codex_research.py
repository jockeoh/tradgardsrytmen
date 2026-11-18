import json
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from . import codex_research


@override_settings(RESEARCH_CODEX_BIN='/test/codex', RESEARCH_CODEX_HOME='/private/cli')
class CodexResearchTests(SimpleTestCase):
    @patch.dict('os.environ', {'OPENAI_API_KEY': 'unused', 'CODEX_API_KEY': 'unused'})
    def test_key_login_is_refused(self):
        with patch('subprocess.run', return_value=CompletedProcess([], 0, '', 'Logged in using an API key')) as run:
            with self.assertRaises(ValueError):
                codex_research.check_login()
        self.assertNotIn('OPENAI_API_KEY', run.call_args.kwargs['env'])
        self.assertNotIn('CODEX_API_KEY', run.call_args.kwargs['env'])

    def test_sources_are_observed_search_results(self):
        def turn(cmd, **kwargs):
            self.assertIn('forced_login_method="chatgpt"', cmd)
            self.assertIn('tools.web_search.allowed_domains=["slu.se"]', cmd)
            Path(cmd[cmd.index('--output-last-message')+1]).write_text('{"summary":"https://made-up.invalid/"}')
            hit = {'type': 'text_result', 'title': 'Källa', 'url': 'https://slu.se/test'}
            event = {'type': 'item.completed', 'item': {'type': 'web_search', 'results': [hit]}}
            return CompletedProcess(cmd, 0, json.dumps(event))
        tool = {'filters': {'allowed_domains': ['slu.se']}, 'user_location': {'country': 'SE', 'city': 'Karlskrona', 'region': 'Blekinge'}}
        body = {'tools': [tool], 'text': {'format': {'schema': {}}}, 'model': 'test', 'input': 'test'}
        with patch('subprocess.run', side_effect=turn):
            response = json.loads(codex_research.execute(body))
        self.assertEqual(response['output'][1]['action']['sources'], [{'title': 'Källa', 'url': 'https://slu.se/test'}])
