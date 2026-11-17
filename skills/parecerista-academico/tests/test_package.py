"""Pacotes incompletos devem falhar antes de serem distribuídos."""

import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_package", ROOT / "scripts/check_package.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "skill"
        shutil.copytree(ROOT, self.root)

    def test_complete_package(self):
        self.assertEqual(checker.inspect(self.root), [])

    def test_missing_routed_reference(self):
        (self.root / "references/saidas.md").unlink()
        self.assertTrue(checker.inspect(self.root))

    def test_unreachable_reference(self):
        (self.root / "references/orphan.md").write_text("# Recurso sem rota\n", encoding="utf-8")
        self.assertTrue(checker.inspect(self.root))

    def test_main_too_long(self):
        with (self.root / "SKILL.md").open("a", encoding="utf-8") as stream:
            stream.write("\n" * 501)
        self.assertTrue(checker.inspect(self.root))

    def test_version_disagrees(self):
        path = self.root / "CITATION.cff"
        path.write_text(path.read_text(encoding="utf-8").replace('version: "2.1.0"', 'version: "2.0.0"'), encoding="utf-8")
        self.assertTrue(checker.inspect(self.root))

    def test_invalid_cases(self):
        path = self.root / "assets/casos-avaliacao.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["cases"][0]["criteria"] = "não é uma lista"
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(checker.inspect(self.root))

    def test_duplicate_case(self):
        path = self.root / "assets/casos-avaliacao.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["cases"].append(data["cases"][0])
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertTrue(checker.inspect(self.root))

    def test_link_cannot_escape_package(self):
        with (self.root / "SKILL.md").open("a", encoding="utf-8") as stream:
            stream.write("\n[Dependência externa](../missing.md)\n")
        self.assertTrue(checker.inspect(self.root))


if __name__ == "__main__":
    unittest.main()
