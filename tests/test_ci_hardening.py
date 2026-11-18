"""Small stdlib CI guard regressions. No installs, archive builds or external calls."""
import ast
import contextlib
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]


def load(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


class CIHardening(unittest.TestCase):
    def test_event_identity_fails_closed(self):
        guard=load('ci_guard');sha='a'*40
        with patch.object(guard,'git',side_effect=[sha,'']):guard.check_identity(sha)
        for expected,returns in [('',[]),(sha,['b'*40]),(sha,[sha,'dirty'])]:
            with patch.object(guard,'git',side_effect=returns),self.assertRaises(ValueError):
                guard.check_identity(expected)

    def test_capacity_and_public_history_fail_closed(self):
        guard=load('ci_guard')
        with patch.object(guard.shutil,'disk_usage',return_value=SimpleNamespace(free=0)),contextlib.redirect_stdout(io.StringIO()),self.assertRaises(ValueError):guard.capacity(8*guard.GIB)
        with patch.object(guard,'check_identity'),patch.object(guard,'private_history',return_value=True),patch.dict(guard.os.environ,{'REPOSITORY_PRIVATE':'false'}),self.assertRaisesRegex(ValueError,'Public validation blocked'):
            guard.preflight()
        with patch.object(guard,'git',return_value='docs/adjudication-v1/COORDINATOR-ONLY.json'):
            self.assertTrue(guard.private_history())

    def test_export_privacy_and_full_workflow_order(self):
        package=load('package_release')
        for rel in ('docs/adjudication-v1/COORDINATOR-ONLY.json','docs/reviewer-responses/reviewer.json','data/private-labels/gold.json'):
            self.assertFalse(package.included(ROOT/rel))
        workflow=(ROOT/'.github/workflows/verify.yml').read_text()
        self.assertEqual(workflow.count('ref: ${{ github.sha }}'),4)
        self.assertEqual(workflow.count('scripts/ci_guard.py preflight'),4)
        self.assertIn('needs: [container-smoke, browser-regression]',workflow)
        for command in ('scripts/release_check.py --require-history','scripts/browser_smoke.py','scripts/browser_attack_smoke.py','scripts/recovery_check.py --browser','scripts/ci_guard.py docker-build','scripts/verify_release.py --require-commit','scripts/ci_guard.py fresh'):
            self.assertIn(command,workflow)
        self.assertNotIn('cache: pip',workflow)
        self.assertEqual(workflow.count('uses: actions/upload-artifact@'),1)
        self.assertIn("if: success() && vars.THREADGATE_ARTIFACT_UPLOAD_APPROVED == 'true'",workflow)
        self.assertIn('retention-days: 1',workflow)
        gate=(ROOT/'scripts/release_check.py').read_text()
        commands=next(n for n in ast.parse(gate).body if isinstance(n,ast.FunctionDef) and n.name=='commands')
        self.assertEqual(len(commands.body[0].value.elts),12)


if __name__=='__main__':unittest.main()
