import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pytest_configure(config):
    generated = ROOT / "fixtures" / "generated"
    needed = {"clean_project.zip", "zipslip.zip", "absolute.zip", "symlink.zip",
              "bomb.zip", "deep.zip", "many.zip"}
    if not generated.is_dir() or not needed <= {p.name for p in generated.glob("*.zip")}:
        subprocess.run([sys.executable, str(ROOT / "fixtures" / "build_fixtures.py")],
                       check=True, cwd=ROOT)
