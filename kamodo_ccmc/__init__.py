import os, sys; sys.path.append(os.path.dirname(os.path.realpath(__file__)))
import warnings

import kamodo # get installed kamodo

# Ensure bundled runtime libs are visible on Windows wheels.
_libs_dir = os.path.join(os.path.dirname(os.path.realpath(__file__)), "libs")
if sys.platform == "win32" and os.path.isdir(_libs_dir):
    if os.environ.get("PATH"):
        if _libs_dir not in os.environ["PATH"]:
            os.environ["PATH"] += os.pathsep + _libs_dir
    else:
        os.environ["PATH"] = _libs_dir
    try:
        os.add_dll_directory(_libs_dir)
    except AttributeError:
        pass

# insert Kamodo class into kamodo namespace
from kamodo.kamodo import Kamodo

import readers
import tools
import flythrough
import filedriver

__version__ = '23.3.2'
