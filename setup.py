from pathlib import Path
import subprocess
import os
import sys

from Cython.Build import cythonize
from setuptools import Extension, setup
from setuptools.command.build_py import build_py


class Build(build_py):
    def run(self):
        root = Path(__file__).resolve().parent
        subprocess.run([sys.executable, str(root / "tools/build_backends.py"), "--backend", os.environ.get("NOTHINGX_BACKEND", "cpp")], check=True)
        super().run()


setup(ext_modules=cythonize([Extension("nothingx." + module, ["nothingx/" + module + ".py"])
                            for module in ("ui", "audio_ui", "artwork")],
                           build_dir="build/cython", compiler_directives={"language_level": 3, "binding": True, "annotation_typing": False}),
      cmdclass={"build_py": Build})
