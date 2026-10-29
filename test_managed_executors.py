"""Version preparation and pointer changes use fake local executors, never models."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from managed_executors import ManagedExecutors, managed_command


class ManagedTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        env=patch.dict(os.environ,{'AGENTBOARD_EXECUTORS_DIR':str(self.root/'fixed')});env.start();self.addCleanup(env.stop)
        self.manager=ManagedExecutors(self.root/'data')
        self.manager.data.mkdir()
        self.state=self.manager.read()
        for slot,version in [('one','1.0.0'),('two','2.0.0')]:
            folder=self.manager.slot_path(self.state,slot)
            (folder/'runtime/npm/bin').mkdir(parents=True)
            (folder/'runtime/npm/bin/npm-cli.js').write_text('// fake',encoding='utf-8')
            (folder/'runtime'/('node.exe' if os.name=='nt' else 'node')).write_text('fake node',encoding='utf-8')
            (folder/'entry.js').write_text('// fake',encoding='utf-8')
            self.state['versions'][slot]={'version':version,'entry':'entry.js','health':{'status':'passed'}}
        self.state['current']='one';self.manager.write(self.state)

    def test_switch_and_rollback_preserve_both_versions(self):
        with patch.object(self.manager,'probe',return_value={'status':'passed'}):
            self.manager.activate('two')
            self.assertEqual(self.manager.read()['previous'],'one')
            self.manager.rollback()
        self.assertEqual(self.manager.read()['current'],'one')
        self.assertEqual(self.manager.read()['previous'],'two')
        self.assertTrue(self.manager.slot_path(self.state,'two').exists())

    def test_failed_check_does_not_change_selected_version(self):
        with patch.object(self.manager,'probe',side_effect=ValueError('fake failure')):
            with self.assertRaises(ValueError):self.manager.activate('two')
        self.assertEqual(self.manager.read()['current'],'one')
        self.assertEqual(self.manager.read()['versions']['two']['health']['status'],'failed')

    def test_missing_pinned_files_fail_instead_of_falling_back(self):
        (self.manager.slot_path(self.state,'one')/'entry.js').unlink()
        with self.assertRaises(RuntimeError):managed_command(self.manager.data)

    def test_prepare_download_is_pinned_and_never_activates(self):
        commands=[]
        def install(command,**kwargs):
            commands.append(command)
            folder=Path(command[command.index('--prefix')+1])
            package=folder/'node_modules/@deepseek-ai/dsh'
            (package/'lib').mkdir(parents=True)
            (package/'lib/bin.js').write_text('// fake',encoding='utf-8')
            (package/'package.json').write_text(json.dumps({'name':'@deepseek-ai/dsh','version':'3.0.0'}),encoding='utf-8')
            return SimpleNamespace(returncode=0)
        with patch.object(self.manager,'_copy_modules',side_effect=lambda src,dst,log: __import__('shutil').copytree(src,dst)), patch.object(self.manager,'probe',return_value={'status':'passed'}), patch('managed_executors.subprocess.run',side_effect=install):
            self.manager._prepare('3.0.0')
        self.assertEqual(self.manager.operation['status'],'ready')
        self.assertEqual(self.manager.read()['current'],'one')
        self.assertIn('--ignore-scripts',commands[0])
        self.assertIn('--save-exact',commands[0])
        self.assertEqual(commands[0][-1],'@deepseek-ai/dsh@3.0.0')

    def test_failed_preparation_keeps_current_and_records_error(self):
        with patch.object(self.manager,'_copy_modules',side_effect=OSError('fake copy failure')):
            self.manager._prepare('3.0.0')
        self.assertEqual(self.manager.operation['status'],'failed')
        self.assertEqual(self.manager.read()['current'],'one')
        self.assertTrue((self.manager.data/'executor-installer.log').exists())

    def test_startup_failure_does_not_remove_previous_version(self):
        self.state['previous']='two';self.manager.write(self.state)
        with patch.object(self.manager,'probe',side_effect=ValueError('fake failure')):
            self.manager.startup_check()
        self.assertEqual(self.manager.read()['current'],'one')
        self.assertEqual(self.manager.read()['previous'],'two')
        self.assertEqual(self.manager.read()['versions']['one']['health']['status'],'failed')

    def test_reject_unpinned_version_and_path_escape(self):
        with self.assertRaises(ValueError):self.manager.start_prepare('latest')
        with self.assertRaises(ValueError):self.manager.slot_path(self.state,'../../outside')


if __name__=='__main__':unittest.main()
