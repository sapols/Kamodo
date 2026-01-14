import importlib.machinery
import os
import shutil
import subprocess
import sys
import warnings

from setuptools import Extension, setup
from setuptools.command.build_ext import build_ext as _build_ext

ROOT = os.path.abspath(os.path.dirname(__file__))
KAMODO_RELEASE = os.environ.get("KAMODO_RELEASE", "").lower() in {"1", "true", "yes"}


def _find_built_extension(directory, module_name):
    for suffix in importlib.machinery.EXTENSION_SUFFIXES:
        candidate = os.path.join(directory, module_name + suffix)
        if os.path.exists(candidate):
            return candidate
    return None


class build_ext(_build_ext):
    def run(self):
        self._outputs = []
        if os.environ.get("KAMODO_SKIP_NATIVE", "").lower() in {"1", "true", "yes"}:
            print("KAMODO_SKIP_NATIVE set: skipping native extensions.")
            return

        self._build_native_extensions()

    def _build_native_extensions(self):
        self._try_build(
            label="OCTREE_BLOCK_GRID (CFFI)",
            func=self._build_cffi_extension,
            rel_dir=os.path.join("kamodo_ccmc", "readers", "OCTREE_BLOCK_GRID"),
            build_script="interpolate_amrdata_extension_build.py",
            module_name="_interpolate_amrdata",
        )
        self._try_build(
            label="Tri2D (CFFI)",
            func=self._build_cffi_extension,
            rel_dir=os.path.join("kamodo_ccmc", "readers", "Tri2D"),
            build_script="interpolate_tri2d_extension_build.py",
            module_name="_interpolate_tri2d",
        )
        self._try_build(
            label="OpenGGCM (f2py)",
            func=self._build_f2py_extension,
            rel_dir=os.path.join("kamodo_ccmc", "readers", "OpenGGCM"),
            module_name="readOpenGGCM",
            sources=["read_b_grids.f", "readmagfile3d.f"],
        )

    def _try_build(self, label, func, **kwargs):
        try:
            built_path = func(**kwargs)
            if built_path:
                self._outputs.append(built_path)
        except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
            message = (
                f"{label} build failed; related reader(s) will be unavailable. "
                "Install a C/Fortran compiler toolchain and reinstall, or set "
                "KAMODO_SKIP_NATIVE=1 to skip these readers."
            )
            if KAMODO_RELEASE:
                raise RuntimeError(message) from exc
            warnings.warn(message)

    def _build_cffi_extension(self, rel_dir, build_script, module_name):
        src_dir = os.path.join(ROOT, rel_dir)
        self._run([sys.executable, build_script], cwd=src_dir)
        return self._copy_built_extension(src_dir, rel_dir, module_name)

    def _build_f2py_extension(self, rel_dir, module_name, sources):
        src_dir = os.path.join(ROOT, rel_dir)
        cmd = [sys.executable, "-m", "numpy.f2py", "-c", "-m", module_name]
        cmd.extend(sources)
        self._run(cmd, cwd=src_dir)
        return self._copy_built_extension(src_dir, rel_dir, module_name)

    def _copy_built_extension(self, src_dir, rel_dir, module_name):
        built = _find_built_extension(src_dir, module_name)
        if not built:
            raise RuntimeError(
                f"Built extension {module_name} not found in {src_dir}."
            )
        dest_dir = os.path.join(os.path.abspath(self.build_lib), rel_dir)
        os.makedirs(dest_dir, exist_ok=True)
        dest_path = os.path.join(dest_dir, os.path.basename(built))
        shutil.copy2(built, dest_path)
        if getattr(self, "editable_mode", False) or getattr(self, "inplace", False):
            src_path = os.path.join(src_dir, os.path.basename(built))
            if os.path.abspath(src_path) != os.path.abspath(built):
                shutil.copy2(built, src_path)
        return dest_path

    def _run(self, cmd, cwd):
        env = os.environ.copy()
        env.setdefault("SETUPTOOLS_USE_DISTUTILS", "stdlib")
        subprocess.check_call(cmd, cwd=cwd, env=env)


if __name__ == "__main__":
    setup(
        ext_modules=[Extension("kamodo_ccmc._native", sources=[])],
        cmdclass={"build_ext": build_ext},
    )
