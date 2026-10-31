import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


class PreparationTests(unittest.TestCase):
    def test_gui_image_reuse_checks_receipt_without_download_or_overwrite(self):
        builder = module('gui_builder_test', 'env/gui/vm/build.py')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); config = root / 'config.json'
            assets = {name: {'source': '/materials/' + name, 'filename': name, 'sha256': 'a' * 64}
                      for name in builder.REQUIRED['linux']}
            config.write_text(json.dumps({'iso': {'source': '/materials/ubuntu.iso', 'sha256': 'b' * 64}, 'assets': assets}))
            disk = root / 'linux-desktop-v1.qcow2'; disk.write_bytes(b'test-disk')
            receipt = root / 'linux-desktop-v1.build.json'
            record = {'sha256': hashlib.sha256(disk.read_bytes()).hexdigest(), 'iso_sha256': 'b' * 64,
                      'asset_sha256': {name: 'a' * 64 for name in assets}}
            receipt.write_text(json.dumps(record))
            args = ['linux', '--config', str(config), '--output', str(root), '--if-missing']
            with patch.dict(os.environ, GUI_BRIDGE_TOKEN='x' * 24, SCIENTIFIC_SOFTWARE_OPERATION_ACCELERATOR='tcg'), \
                 patch.object(builder.shutil, 'which', return_value='/unused/tool'), \
                 patch.object(builder, 'acquire', side_effect=AssertionError('download')), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(builder.main(args), 0)
                record['sha256'] = 'c' * 64; receipt.write_text(json.dumps(record))
                with self.assertRaises(SystemExit): builder.main(args)
            self.assertEqual(disk.read_bytes(), b'test-disk')

    def test_end_to_end_prepare_keeps_existing_images(self):
        manager = module('closeloop_manager_test', 'env/closeloop/manage.py')
        with patch.object(manager, 'verify_frozen'), \
             patch.object(manager.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run, \
             contextlib.redirect_stdout(io.StringIO()):
            manager.build()
        self.assertFalse(any('build' in call.args[0] for call in run.call_args_list))

    def test_end_to_end_prepare_builds_only_missing_verifier(self):
        manager = module('closeloop_manager_partial_test', 'env/closeloop/manage.py')
        def execute(command, **kwargs):
            missing = command[1:3] == ['image', 'inspect'] and 'verifier' in command[-1]
            return SimpleNamespace(returncode=int(missing))
        with patch.object(manager, 'verify_frozen'), patch.object(manager.subprocess, 'run', side_effect=execute) as run, \
             contextlib.redirect_stdout(io.StringIO()):
            manager.build()
        builds = [call.args[0] for call in run.call_args_list if call.args[0][1] == 'build']
        self.assertEqual(len(builds), 1)
        self.assertIn('verifier', builds[0][builds[0].index('-t') + 1])

    def test_fetch_downloads_only_selected_missing_paths_and_verifies_bytes(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        self.addCleanup(lambda: sys.path.remove(str(ROOT / 'scripts')))
        fetcher = module('fetch_task_data_test', 'scripts/fetch_task_data.py')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); checkout = root / 'checkout'; snapshot = root / 'snapshot'
            release = checkout / 'releases/v1'; release.mkdir(parents=True)
            (release / 'release.json').write_text(json.dumps({'datasets': {'data': 'test/data', 'reference': 'test/reference'}}))
            name = 'tasks/protocol-planning/selected/tests/gold.json'
            source = snapshot / name; source.parent.mkdir(parents=True); source.write_bytes(b'{"value": 1}\n')
            member = {'dataset': 'reference', 'path': name, 'size': source.stat().st_size,
                      'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
            with patch.object(fetcher, 'ROOT', checkout), patch.object(fetcher, 'RELEASE', release), \
                 patch.object(fetcher, 'select_tasks', return_value=[]), \
                 patch.object(fetcher, 'members_for_tasks', return_value=[member]), \
                 patch('huggingface_hub.snapshot_download', return_value=str(snapshot)) as download, \
                 patch.object(sys, 'argv', ['fetch_task_data.py', '--tasks', 'selected.txt']), \
                 contextlib.redirect_stdout(io.StringIO()):
                fetcher.main()
            self.assertEqual(download.call_count, 1)
            self.assertEqual(download.call_args.kwargs['allow_patterns'], [name])
            self.assertEqual((checkout / name).read_bytes(), source.read_bytes())


if __name__ == '__main__':
    unittest.main()
