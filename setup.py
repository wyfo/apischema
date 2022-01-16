import pathlib
import platform
import sys
import warnings

# The following code is copied from
# https://github.com/tornadoweb/tornado/blob/master/setup.py
# to support installing without the extension on platforms where
# no compiler is available.
from distutils.command.build_ext import build_ext

from setuptools import Extension, find_packages, setup


class custom_build_ext(build_ext):
    """Allow C extension building to fail.
    The C extension speeds up (de)serialization, but is not essential.
    """

    warning_message = """
********************************************************************
WARNING: %s could not
be compiled. No C extensions are essential for apischema to run,
although they do result in significant speed improvements for
(de)serialization.
%s
Here are some hints for popular operating systems:
If you are seeing this message on Linux you probably need to
install GCC and/or the Python development package for your
version of Python.
Debian and Ubuntu users should issue the following command:
    $ sudo apt-get install build-essential python-dev
RedHat and CentOS users should issue the following command:
    $ sudo yum install gcc python-devel
Fedora users should issue the following command:
    $ sudo dnf install gcc python-devel
MacOS users should run:
    $ xcode-select --install
********************************************************************
"""

    def run(self):
        try:
            build_ext.run(self)
        except Exception:
            e = sys.exc_info()[1]
            sys.stdout.write("%s\n" % str(e))
            warnings.warn(
                self.warning_message
                % (
                    "Extension modules",
                    "There was an issue with "
                    "your platform configuration"
                    " - see above.",
                )
            )

    def build_extension(self, ext):
        name = ext.name
        try:
            build_ext.build_extension(self, ext)
        except Exception:
            e = sys.exc_info()[1]
            sys.stdout.write("%s\n" % str(e))
            warnings.warn(
                self.warning_message
                % (
                    "The %s extension " "module" % (name,),
                    "The output above "
                    "this warning shows how "
                    "the compilation "
                    "failed.",
                )
            )


ext_modules = None
# Cythonization makes apischema a lot slower using PyPy
if platform.python_implementation() != "PyPy":
    ext_modules = [
        Extension(
            f"apischema.{package}.methods", sources=[f"apischema/{package}/methods.c"]
        )
        for package in ("deserialization", "serialization")
    ]

setup(
    name="apischema",
    version="0.17.3",
    url="https://github.com/wyfo/apischema",
    author="Joseph Perez",
    author_email="joperez@hotmail.fr",
    license="MIT",
    packages=find_packages(include=["apischema*"]),
    package_data={
        "apischema": ["py.typed"],
        "apischema.deserialization": ["methods.pyx"],
        "apischema.serialization": ["methods.pyx"],
    },
    description="JSON (de)serialization, GraphQL and JSON schema generation using Python typing.",
    long_description=pathlib.Path("README.md").read_text(),
    long_description_content_type="text/markdown",
    python_requires=">=3.6",
    install_requires=["dataclasses>=0.7;python_version<'3.7'"],
    extras_require={
        "graphql": ["graphql-core>=3.0.0"],
        "examples": [
            "graphql-core>=3.0.0",
            "attrs",
            "docstring_parser",
            "bson",
            "orjson",
            "pydantic",
            "pytest",
            "sqlalchemy",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    cmdclass={"build_ext": custom_build_ext},
    ext_modules=ext_modules,
)
