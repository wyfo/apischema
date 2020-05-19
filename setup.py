from setuptools import find_packages, setup

with open("README.md") as f:
    README = f.read()

# cannot use Cython because of https://github.com/cython/cython/issues/3537
setup(
    name='apischema',
    url="https://github.com/wyfo/apischema",
    author="Joseph Perez",
    author_email="joperez@hotmail.fr",
    description="Another Python API schema handling and JSON (de)serialization "
                "through typing annotation; light, simple, powerful.",
    long_description=README,
    long_description_content_type="text/markdown",
    version='0.2.0',
    license='MIT',
    packages=find_packages(include=["apischema*"]),
    classifiers=[
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
    python_requires='>=3.7'
)
