#!/usr/bin/env bash
python3 -m pip install -r $(dirname $0)/requirements.cython.txt
$(dirname $0)/cythonize.py