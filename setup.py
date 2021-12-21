from setuptools import find_packages, setup

with open("README.md") as f:
    README = f.read()

setup(
    name="apischema",
    version="0.15.9",
    url="https://github.com/wyfo/apischema",
    author="Joseph Perez",
    author_email="joperez@hotmail.fr",
    license="MIT",
    packages=find_packages(include=["apischema*"]),
    package_data={"apischema": ["py.typed"]},
    description="JSON (de)serialization + GraphQL and JSON schema generation through python typing, with a spoonful of sugar.",
    long_description=README,
    long_description_content_type="text/markdown",
    python_requires=">=3.6",
    install_requires=["dataclasses==0.7;python_version<'3.7'"],
    extras_require={
        "graphql": ["graphql-core>=3.1.2"],
        "examples": [
            "graphql-core>=3.1.2",
            "pytest>=6.2.2",
            "pydantic>=1.7.3",
            "attrs>=20.3.0",
            "sqlalchemy>=1.3.23",
            "bson>=0.5.10",
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
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
)
