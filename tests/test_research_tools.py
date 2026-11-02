import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from agents import argv
from browser_tools import browser_server, research_capabilities, BROWSER_TOOLS


class ResearchToolsTests(unittest.TestCase):
    def test_missing_browser_does_not_disable_web_research(self):
        with tempfile.TemporaryDirectory() as folder, patch('browser_tools.runtime_root', return_value=Path(folder)), patch('shutil.which', return_value='/bin/agent'):
            self.assertEqual(research_capabilities()['browser'], 'not-installed')
            codex = argv('codex')
            self.assertIn('web_search="live"', codex)
            self.assertEqual(codex[codex.index('--sandbox') + 1], 'read-only')
            claude = argv('claude')
            self.assertEqual(json.loads(claude[claude.index('--mcp-config') + 1]), {'mcpServers': {}})
            self.assertEqual(claude[claude.index('--allowedTools') + 1], 'WebSearch,WebFetch')

    def test_both_agents_share_task_profile_without_native_config_changes(self):
        with tempfile.TemporaryDirectory() as folder, patch('browser_tools.runtime_root', return_value=Path(folder)), patch('shutil.which', return_value='/bin/agent'):
            cli = Path(folder) / 'node_modules/@playwright/mcp/cli.js'
            cli.parent.mkdir(parents=True); cli.touch()
            server = browser_server('task-one')
            self.assertNotEqual(server['args'], browser_server('task-two')['args'])
            codex = argv('codex', task_id='task-one')
            settings = dict(value.split('=', 1) for value in codex if value.startswith('mcp_servers.acc_browser.'))
            self.assertEqual(json.loads(settings['mcp_servers.acc_browser.args']), server['args'])
            self.assertEqual(json.loads(settings['mcp_servers.acc_browser.enabled_tools']), BROWSER_TOOLS)
            claude = argv('claude', task_id='task-one')
            self.assertEqual(json.loads(claude[claude.index('--mcp-config') + 1])['mcpServers']['acc_browser'], server)
            allowed = claude[claude.index('--allowedTools') + 1]
            self.assertNotIn('browser_run_code', allowed)
            self.assertNotIn('Bash', allowed)
            self.assertIn('mcp__acc_browser__browser_snapshot', allowed)
            self.assertEqual(research_capabilities()['browser'], 'configured-unverified')
