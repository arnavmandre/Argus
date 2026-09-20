import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from api.env import load_local_env


class LocalEnvTests(unittest.TestCase):
    def test_loads_root_env_without_overwriting_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "# local secret\nGROQ_API_KEY='from-file'\nEXISTING=file\n",
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {"EXISTING": "shell"}, clear=True):
                self.assertTrue(load_local_env(path))
                self.assertEqual(os.environ["GROQ_API_KEY"], "from-file")
                self.assertEqual(os.environ["EXISTING"], "shell")

    def test_missing_file_is_optional(self):
        self.assertFalse(load_local_env(Path("definitely-missing.env")))


if __name__ == "__main__":
    unittest.main()
