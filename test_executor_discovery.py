"""Offline discovery must never invoke npm or download an executor."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import executor_discovery as discovery


class DiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        environment = patch.dict(os.environ, {"AGENTBOARD_DEEPSEEK_ENTRY":"", "APPDATA":"", "LOCALAPPDATA":"", "NPM_CONFIG_CACHE":"", "npm_config_cache":str(self.root)})
        environment.start()
        self.addCleanup(environment.stop)
        home = patch.object(discovery.Path, "home", return_value=self.root)
        home.start()
        self.addCleanup(home.stop)

    def test_installed_command_keeps_priority(self):
        with patch.object(discovery.shutil, "which", return_value="dsh"):
            self.assertEqual(discovery.deepseek_command(), ["dsh"])

    def test_cached_entry_is_invoked_directly_with_node(self):
        package = self.root/'_npx'/'cache'/ 'node_modules'/'@deepseek-ai'/'dsh'
        (package/'lib').mkdir(parents=True)
        (package/'lib/bin.js').write_text('// offline fixture',encoding='utf-8')
        (package/'package.json').write_text(json.dumps({'name':'@deepseek-ai/dsh','bin':{'dsh':'lib/bin.js'}}),encoding='utf-8')
        with patch.object(discovery.shutil,'which',side_effect=lambda name:'node' if name.startswith('node') else None):
            self.assertEqual(discovery.deepseek_command(),['node',str((package/'lib/bin.js').resolve())])

    def test_npx_alone_is_not_a_ready_executor(self):
        with patch.object(discovery.shutil,'which',side_effect=lambda name:'npx' if name.startswith('npx') else None):
            self.assertFalse(discovery.deepseek_available())
            with self.assertRaises(RuntimeError):
                discovery.deepseek_command()

    def test_explicit_entry_is_validated(self):
        with patch.dict(os.environ,{'AGENTBOARD_DEEPSEEK_ENTRY':str(self.root/'missing.js')}):
            with self.assertRaises(RuntimeError):
                discovery.deepseek_command()

    def test_cache_entry_cannot_escape_package_root(self):
        package = self.root/'_npx'/'cache'/'node_modules'/'@deepseek-ai'/'dsh'
        package.mkdir(parents=True)
        (package/'package.json').write_text(json.dumps({'name':'@deepseek-ai/dsh','bin':'../../../../outside.js'}),encoding='utf-8')
        (package/'../../../../outside.js').resolve().write_text('// fixture',encoding='utf-8')
        with patch.object(discovery.shutil,'which',side_effect=lambda name:'node' if name.startswith('node') else None):
            self.assertFalse(discovery.deepseek_available())


if __name__ == '__main__':
    unittest.main()
