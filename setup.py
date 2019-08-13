from setuptools import find_packages, setup

with open("README.md") as f:
    README = f.read()

setup(
    name='pyapischema',
    url="https://github.com/wyfo/apischema",
    author="Joseph Perez",
    author_email="joperez@hotmail.fr",
    description="Another Python API schema handling through typing annotation;"
                " light, simple, powerful.",
    long_description=README,
    long_description_content_type="text/markdown",
    version='1.0.0',
    packages=find_packages(include=["apischema"]),
    install_requires=["tmv", "pyhumps"],
    classifiers=[
        "Programming Language :: Python :: 3.7",
    ],
)
