"""Build hook: ship the canonical skills/ tree inside the wheel as research_toolkit/_skills so `rtk setup` works
after a plain `pip install` (no Node.js, no git clone). All other metadata lives in pyproject.toml."""
import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


class build_py_with_skills(build_py):
    def run(self):
        super().run()
        src = Path(__file__).parent / "skills"
        if src.is_dir():
            dest = Path(self.build_lib) / "research_toolkit" / "_skills"
            shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(src, dest)


setup(cmdclass={"build_py": build_py_with_skills})
