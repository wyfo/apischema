#!/usr/bin/env bash
python3 -m pip install -r $(dirname $0)/requirements.txt
$(dirname $0)/cythonize.py