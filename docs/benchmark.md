# Benchmark

!!! note
    Benchmark presented is just [*Pydantic* benchmark](https://github.com/samuelcolvin/pydantic/tree/master/benchmarks) where *Apischema* has been ["inserted"](https://github.com/wyfo/pydantic/tree/benchmark_apischema). Benchmark is run **without *Cython* compilation**.

Below are the results of crude benchmark comparing *apischema* to *pydantic* and other validation libraries.

Package | Version | Relative Performance | Mean deserialization time
--- | --- | --- | ---
apischema | `0.11` |  | 50.7μs
valideer | `0.4.2` | 2.3x slower | 118.2μs
pydantic | `1.7.2` | 2.4x slower | 120.1μs
attrs + cattrs | `20.2.0` | 2.5x slower | 125.6μs
marshmallow | `3.8.0` | 3.9x slower | 198.1μs
voluptuous | `0.12.0` | 5.1x slower | 257.6μs
trafaret | `2.1.0` | 5.5x slower | 280.6μs
django-rest-framework | `3.12.1` | 20.0x slower | 1016.4μs
cerberus | `1.3.2` | 40.3x slower | 2043.3μs

Package | Version | Relative Performance | Mean serialization time
--- | --- | --- | ---
apischema | `0.1` |  | 24.8μs
pydantic | `1.7.2` | 2.3x slower | 57.5μs

Benchmarks were run with Python 3.8 (*CPython*) and the package versions listed above installed via *pypi* on *macOs* 10.15.7

!!! note
    A few precisions have to be written about these results:
    
    - *pydantic* version executed is not *Cythonised*; by the way, even with *Cython*, *Apischema* is still faster than *pydantic*
    - *Apischema* is optimized enough to not have a real performance improvement using *Pypy* instead of *CPython*
    - *pydantic* benchmark is biased by the implementation of `datetime` parsing for *cattrs* (see [this post](https://stefan.sofa-rockers.org/2020/05/29/attrs-dataclasses-pydantic/) about it); in fact, if *cattrs* use a decently fast implementation, like the standard `datetime.fromisoformat`, *cattrs* becomes 3 times faster than *pydantic*, even faster than *Apischema*. Of course, you don't get the same features, like complete error handling, aggregate fields, etc. In fact, performance difference between *Apischema* and *cattrs* comes mostly of error handling (*cattrs* doesn't catch errors to gather them) and the gap between them is a lot reduced when playing benchmark only on valid cases.
    
    
## FAQ

#### Why not ask directly for integration to *pydantic* benchmark?
[Done, but rejected](https://github.com/samuelcolvin/pydantic/pull/1525#issuecomment-630422702) because "apischema doesn't have enough usage". Let's change that!

