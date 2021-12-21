from setuptools import find_packages, setup

with open("README.md") as f:
    README = f.read()

setup(
    name="apischema",
    version="0.16.6",
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
    install_requires=["dataclasses==0.7;python_version<'3.7'"],
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
)
