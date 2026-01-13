import glob
import importlib.machinery
import os
import shutil
import subprocess
import sys

from setuptools import setup
from setuptools.command.build_py import build_py as _build_py

ROOT = os.path.abspath(os.path.dirname(__file__))


def _find_built_extension(directory, module_name):
    for suffix in importlib.machinery.EXTENSION_SUFFIXES:
        candidate = os.path.join(directory, module_name + suffix)
        if os.path.exists(candidate):
            return candidate
    return None


class build_py(_build_py):
    _native_built = False

    def run(self):
        if not self.__class__._native_built:
            self.__class__._native_built = True
            self._build_native_extensions()
        super().run()

    def _build_native_extensions(self):
        if os.environ.get("KAMODO_SKIP_NATIVE", "").lower() in {"1", "true", "yes"}:
            print("KAMODO_SKIP_NATIVE set: skipping native extensions.")
            return

        try:
            self._build_cffi_extension(
                rel_dir=os.path.join("kamodo_ccmc", "readers", "OCTREE_BLOCK_GRID"),
                build_script="interpolate_amrdata_extension_build.py",
                module_name="_interpolate_amrdata",
            )
            self._build_cffi_extension(
                rel_dir=os.path.join("kamodo_ccmc", "readers", "Tri2D"),
                build_script="interpolate_tri2d_extension_build.py",
                module_name="_interpolate_tri2d",
            )
            self._build_f2py_extension(
                rel_dir=os.path.join("kamodo_ccmc", "readers", "OpenGGCM"),
                module_name="readOpenGGCM",
                sources=["read_b_grids.f", "readmagfile3d.f"],
            )
        except (OSError, subprocess.CalledProcessError) as exc:
            raise RuntimeError(
                "Native extension build failed. Install a C/Fortran compiler "
                "toolchain or set KAMODO_SKIP_NATIVE=1 to skip these readers."
            ) from exc

    def _build_cffi_extension(self, rel_dir, build_script, module_name):
        src_dir = os.path.join(ROOT, rel_dir)
        self._run([sys.executable, build_script], cwd=src_dir)
        self._copy_built_extension(src_dir, rel_dir, module_name)

    def _build_f2py_extension(self, rel_dir, module_name, sources):
        src_dir = os.path.join(ROOT, rel_dir)
        cmd = [sys.executable, "-m", "numpy.f2py", "-c", "-m", module_name]
        cmd.extend(sources)
        self._run(cmd, cwd=src_dir)
        self._copy_built_extension(src_dir, rel_dir, module_name)

    def _copy_built_extension(self, src_dir, rel_dir, module_name):
        built = _find_built_extension(src_dir, module_name)
        if not built:
            raise RuntimeError(
                f"Built extension {module_name} not found in {src_dir}."
            )
        dest_dir = os.path.join(os.path.abspath(self.build_lib), rel_dir)
        os.makedirs(dest_dir, exist_ok=True)
        shutil.copy2(built, dest_dir)

    def _run(self, cmd, cwd):
        subprocess.check_call(cmd, cwd=cwd)


if __name__ == "__main__":
    setup(cmdclass={"build_py": build_py})
