from pathlib import Path
import subprocess

from Cython.Build import cythonize
from setuptools import Extension, setup
from setuptools.command.build_py import build_py


class Build(build_py):
    def run(self):
        root = Path(__file__).resolve().parent
        subprocess.run(["cmake", "-S", str(root / "native"), "-B", str(root / "build/native"), "-DCMAKE_BUILD_TYPE=Release"], check=True)
        subprocess.run(["cmake", "--build", str(root / "build/native"), "-j2"], check=True)
        self.mkpath(str(root / "nothingx/bin"))
        self.copy_file(str(root / "build/native/nothingx-core"), str(root / "nothingx/bin/nothingx-core"))
        super().run()


setup(ext_modules=cythonize([Extension("nothingx." + module, ["nothingx/" + module + ".py"])
                            for module in ("ui", "audio_ui", "artwork")],
                           build_dir="build/cython", compiler_directives={"language_level": 3, "binding": True, "annotation_typing": False}),
      cmdclass={"build_py": Build})
