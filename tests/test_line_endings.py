"""Ensure Git checks out reproducible generated files on Windows too."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(shutil.which("git"), "Git is needed to test checkout attributes")
class CheckoutLineEndingsTests(unittest.TestCase):
    def test_autocrlf_checkout_keeps_generated_lf_and_binary_bytes(self):
        with tempfile.TemporaryDirectory(prefix="xait-checkout-") as directory:
            repo = Path(directory)
            subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
            subprocess.run(["git", "config", "core.autocrlf", "true"], cwd=repo, check=True)
            shutil.copyfile(ROOT / ".gitattributes", repo / ".gitattributes")
            files = {
                "docs/index.html": b"first line\nsecond line\n",
                "docs/assets/vendor/supabase-2.118.0.js": b"upstream\r\nbytes\r\n",
                "assets/screenshots/sample.png": b"\x89PNG\r\n\x1a\nexample\r\n",
            }
            for name, content in files.items():
                path = repo / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content)
            subprocess.run(["git", "add", "--", ".gitattributes", *files], cwd=repo,
                           check=True, capture_output=True)
            for name in files:
                (repo / name).unlink()
            subprocess.run(["git", "checkout", "--", *files], cwd=repo,
                           check=True, capture_output=True)
            for name, expected in files.items():
                with self.subTest(path=name):
                    self.assertEqual((repo / name).read_bytes(), expected)


if __name__ == "__main__":
    unittest.main()
