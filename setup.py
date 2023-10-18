import platform

from setuptools import Extension, setup

from scripts import cythonize

cythonize.main()

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
