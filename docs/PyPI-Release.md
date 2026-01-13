# PyPI Release Checklist (modeled after SpacePy)

This checklist mirrors SpacePy's `DISTRIBUTE` workflow: build a clean sdist on
Unix, then build platform wheels, test, and upload. Kamodo includes native
extensions (CFFI + f2py), so wheels are the primary "pip install just works"
delivery.

## 1) Prepare the release
- Update version in `setup.cfg`.
- Update any docs or changelog entries.
- Tag the release commit (or create a release branch) after review.

## 2) Build the sdist (Unix)
- Use a clean build environment.
- Ensure build dependencies are installed (numpy<2, cffi, setuptools, wheel).
- Build the sdist:
  - `python -m build -s`
- Confirm the sdist contains native sources:
  - C/C++ from `kamodo_ccmc/readers/OCTREE_BLOCK_GRID/` and `kamodo_ccmc/readers/Tri2D/`
  - Fortran from `kamodo_ccmc/readers/OpenGGCM/`

## 3) Build wheels (multiple OS)
SpacePy builds wheels on Linux, macOS, and Windows so users do not need local
compilers. For Kamodo, follow the same approach:

- Linux: build manylinux wheels (e.g., manylinux2014).
- macOS: build wheels for x86_64 and arm64.
- Windows: build wheels with a working gfortran toolchain (e.g., via MSYS2 or
  a preconfigured conda build environment).

If using GitHub Actions, run the `cibuildwheel` workflow from this repo to
produce wheel artifacts.

## 4) Test wheels
- Create fresh environments and install wheels:
  - `pip install kamodo-ccmc`
- Run at least one reader that touches native code:
  - SWMF GM (CFFI), GAMERA (CFFI), OpenGGCM (f2py)

## 5) Upload
- Upload to TestPyPI first.
- Validate install from TestPyPI.
- Upload to PyPI after verification.

## Notes
- Set `KAMODO_SKIP_NATIVE=1` only for debugging; it skips building readers that
  depend on compiled extensions.
- This process is inspired by SpacePy's `DISTRIBUTE` guidance and the way
  SpacePy ships platform wheels for Fortran/C dependencies.
