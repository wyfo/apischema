import os
import platform
import sys

from setuptools import find_packages, setup

import scripts.generate_pyx

README = None
# README cannot be read by older python version run by tox
if "TOX_ENV_NAME" not in os.environ:
    with open("README.md") as f:
        README = f.read()


ext_modules = None
if "clean" in sys.argv:
    scripts.generate_pyx.clean()
if (
    not any(arg in sys.argv for arg in ["clean", "check"])
    and "SKIP_CYTHON" not in os.environ
    and platform.python_implementation() != "PyPy"
):
    try:
        from Cython.Build import cythonize
    except ImportError:
        pass
    else:
        scripts.generate_pyx.main()
        os.environ["CFLAGS"] = "-O3 " + os.environ.get("CFLAGS", "")
        ext_modules = cythonize(["apischema/**/*.pyx"], language_level=3)

setup(
    name="apischema",
    version="0.16.1",
    url="https://github.com/wyfo/apischema",
    author="Joseph Perez",
    author_email="joperez@hotmail.fr",
    license="MIT",
    packages=find_packages(include=["apischema*"]),
    package_data={"apischema": ["py.typed"]},
    description="JSON (de)serialization, *GraphQL* and JSON schema generation using Python typing.",
    long_description=README,
    long_description_content_type="text/markdown",
    python_requires=">=3.6",
    install_requires=["dataclasses>=0.7;python_version<'3.7'"],
    extras_require={
        "graphql": ["graphql-core>=3.1.2"],
        "examples": [
            "graphql-core>=3.1.2",
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
    ext_modules=ext_modules,
)
