"""Download the official TexasSolver Windows release into tools/texassolver/bin."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.solver import install_windows_release, status

if __name__ == "__main__":
    print("Downloading TexasSolver v0.2.0 (Windows)…")
    result = install_windows_release()
    print(result)
    print("Installed:" if status()["installed"] else "FAILED")
    print(status()["console"])
