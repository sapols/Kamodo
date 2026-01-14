import importlib.machinery
import os
import shutil
import subprocess
import sys
import warnings

from setuptools import setup
from setuptools.command.build import build as _build
from setuptools.command.build_ext import build_ext as _build_ext
from setuptools.command.build_py import build_py as _build_py

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
        self._bundle_runtime_libs()

    def _bundle_runtime_libs(self):
        if sys.platform == "darwin":
            outdir = os.path.join(os.path.abspath(self.build_lib), "kamodo_ccmc")
            libs = _copy_macos_fortran_libs(outdir, strict=KAMODO_RELEASE)
            self._outputs.extend(libs)
            for output in self._outputs:
                if output.endswith(".so"):
                    _add_macos_rpath(output, strict=KAMODO_RELEASE)
        elif sys.platform == "win32":
            outdir = os.path.join(os.path.abspath(self.build_lib), "kamodo_ccmc")
            libs = _copy_windows_fortran_libs(outdir, strict=KAMODO_RELEASE)
            self._outputs.extend(libs)

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
        if "SETUPTOOLS_USE_DISTUTILS" not in env:
            if sys.version_info >= (3, 12):
                env["SETUPTOOLS_USE_DISTUTILS"] = "local"
            else:
                env["SETUPTOOLS_USE_DISTUTILS"] = "stdlib"
        subprocess.check_call(cmd, cwd=cwd, env=env)

    def get_outputs(self):
        outputs = super().get_outputs() or []
        outputs.extend(self._outputs)
        return outputs


class build(_build):
    sub_commands = [
        ("build_ext", lambda self: True),
        ("build_py", _build.has_pure_modules),
        ("build_clib", _build.has_c_libraries),
        ("build_scripts", _build.has_scripts),
    ]


class build_py(_build_py):
    def run(self):
        if not self.distribution.have_run.get("build_ext"):
            self.run_command("build_ext")
        build_ext_cmd = self.get_finalized_command("build_ext")
        editable = getattr(build_ext_cmd, "editable_mode", False) or getattr(
            build_ext_cmd, "inplace", False
        )
        if not editable:
            _clean_source_artifacts()
        super().run()
        outputs = list(getattr(self, "_outputs", []))
        for output in getattr(build_ext_cmd, "_outputs", []):
            if output not in outputs:
                outputs.append(output)
        self._outputs = outputs


def _copy_macos_fortran_libs(outdir, strict):
    libnames = ["libgfortran", "libquadmath", "libgcc_s.1", "libgcc_s.1.1"]
    outlibdir = os.path.join(outdir, "libs")
    os.makedirs(outlibdir, exist_ok=True)
    outputs = []
    for lib in libnames:
        proc = subprocess.run(
            ["gfortran", f"--print-file-name={lib}.dylib"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if proc.returncode != 0:
            if strict:
                raise RuntimeError(f"Failed locating {lib}.dylib via gfortran.")
            warnings.warn(f"Skipping missing {lib}.dylib (gfortran not available).")
            continue
        libpath = proc.stdout.strip()
        if not os.path.isfile(libpath):
            if lib.startswith("libgcc_s"):
                continue
            if strict:
                raise RuntimeError(f"Required runtime library not found: {libpath}")
            warnings.warn(f"Skipping missing {lib}.dylib at {libpath}.")
            continue
        libpath = os.path.realpath(libpath)
        dest = os.path.join(outlibdir, os.path.basename(libpath))
        shutil.copy2(libpath, dest)
        outputs.append(dest)
    return outputs


def _clean_source_artifacts():
    for root, _, files in os.walk(os.path.join(ROOT, "kamodo_ccmc", "readers")):
        for filename in files:
            if filename.endswith((".o", ".so")):
                try:
                    os.remove(os.path.join(root, filename))
                except OSError:
                    pass


def _add_macos_rpath(path, strict):
    cmd = ["install_name_tool", "-add_rpath", "@loader_path/../libs", path]
    try:
        subprocess.check_call(cmd)
    except (OSError, subprocess.CalledProcessError) as exc:
        if strict:
            raise RuntimeError(f"Failed adding rpath to {path}.") from exc
        warnings.warn(f"Failed adding rpath to {path}; runtime libs may not load.")


def _copy_windows_fortran_libs(outdir, strict):
    outputs = []
    libneeded = ("libgfortran", "libgcc_s", "libquadmath")
    liboptional = ("libwinpthread",)
    libdir = None
    libnames = None
    for p in os.environ.get("PATH", "").split(os.pathsep):
        if not os.path.isdir(p):
            continue
        entries = sorted(
            f for f in os.listdir(p) if f.lower().endswith(".dll")
        )
        needed = {}
        for prefix in libneeded:
            for f in entries:
                if f.lower().startswith(prefix):
                    needed[prefix] = f
                    break
        if len(needed) == len(libneeded):
            libdir = p
            libnames = list(needed.values())
            for f in entries:
                if f.lower().startswith(liboptional):
                    libnames.append(f)
            break
    if libdir is None:
        if strict:
            raise RuntimeError("Could not locate Fortran runtime DLLs on PATH.")
        warnings.warn("Fortran runtime DLLs not found; Windows wheels may be incomplete.")
        return outputs
    outlibdir = os.path.join(outdir, "libs")
    os.makedirs(outlibdir, exist_ok=True)
    for f in libnames:
        src = os.path.join(libdir, f)
        dest = os.path.join(outlibdir, f)
        shutil.copy2(src, dest)
        outputs.append(dest)
    return outputs


if __name__ == "__main__":
    setup(cmdclass={"build": build, "build_ext": build_ext, "build_py": build_py})
