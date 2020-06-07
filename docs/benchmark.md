# Benchmark

!!! note
    Benchmark presented is just [*Pydantic* benchmark](https://github.com/samuelcolvin/pydantic/tree/master/benchmarks) where *Apischema* has been ["inserted"](https://github.com/wyfo/pydantic/tree/benchmark_apischema). Benchmark is run **without *Cython* compilation**.

Below are the results of crude benchmark comparing *apischema* to *pydantic* and other validation libraries.

Package | Version | Relative Performance | Mean deserialization time
--- | --- | --- | ---
apischema | `0.7.0` |  | 108.0μs
pydantic | `1.6.1` | 1.1x slower | 119.5μs
attrs + cattrs | `19.1.0` | 1.1x slower | 123.1μs
valideer | `0.4.2` | 1.2x slower | 124.5μs
marshmallow | `3.5.2` | 1.9x slower | 203.9μs
voluptuous | `0.11.7` | 2.4x slower | 254.2μs
trafaret | `1.2.0` | 2.9x slower | 312.2μs
django-rest-framework | `3.10.2` | 8.4x slower | 911.3μs
cerberus | `1.3.2` | 22.4x slower | 2416.6μs

Package | Version | Relative Performance | Mean serialization time
--- | --- | --- | ---
apischema | `0.7.0` |  | 29.3μs
pydantic | `1.6.1` | 2.0x slower | 58.2μs

Benchmarks were run with Python 3.7.7 (CPython) and the package versions listed above installed via pypi on macOs 10.15.5
    
!!! note
    Using *PyPy*, *Apischema* lead is even more confirmed. 

## FAQ

#### Why not use *Cython*?
*Cython* doesn't support yet some of the modern Python features like `Generic` or `dataclass` which are intensively used in *Apischema*.

!!! note
    With some hacks, it has been possible to cythonize some of the modules, with performance increase; it becomes then a little bit slower than cythonized *Pydantic* (which is optimized for *Cython*). But this is too dirty to keep it, and *Cython* is not a priority.


#### Why not ask for integration to *pydantic* benchmark?
[Done, but rejected](https://github.com/samuelcolvin/pydantic/pull/1525#issuecomment-630422702) because "apischema doesn't have enough usage". Let's change that!

