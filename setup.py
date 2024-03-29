import os
import platform

from setuptools import Extension, setup

ext_modules = [
    Extension(
        f"apischema.{package}.methods",
        sources=[f"apischema/{package}/methods.c"],
        optional=True,
    )
    for package in ("deserialization", "serialization")
    # Cythonization makes apischema slower using PyPy
    if platform.python_implementation() != "PyPy" and "NO_EXTENSION" not in os.environ
]
setup(ext_modules=ext_modules)
