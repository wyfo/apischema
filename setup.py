import importlib
import os
import platform
import sys

from setuptools import Extension, setup

sys.path.append(os.path.dirname(__file__))
importlib.import_module("scripts.cythonize").main()

ext_modules = [
    Extension(
        f"apischema.{package}.methods",
        sources=[f"apischema/{package}/methods.c"],
        optional=True,
    )
    for package in ("deserialization", "serialization")
    # Cythonization makes apischema slower using PyPy
    if platform.python_implementation() != "PyPy"
]
setup(ext_modules=ext_modules)
