# Benchmark

!!! note
    Benchmark presented is just [*Pydantic* benchmark](https://github.com/samuelcolvin/pydantic/tree/master/benchmarks) where *apischema* has been ["inserted"](https://github.com/wyfo/pydantic/tree/benchmark_apischema).

Below are the results of crude benchmark comparing *apischema* to *pydantic* and other validation libraries.

Package | Version | Relative Performance | Mean deserialization time
--- | --- | --- | ---
apischema | `0.14.0` |  | 51.6μs
pydantic | `1.7.3` | 1.5x slower | 77.8μs
valideer | `0.4.2` | 2.3x slower | 119.4μs
attrs + cattrs | `20.2.0` | 2.4x slower | 122.2μs
marshmallow | `3.8.0` | 4.0x slower | 204.7μs
voluptuous | `0.12.0` | 4.9x slower | 254.9μs
trafaret | `2.1.0` | 5.5x slower | 281.4μs
django-rest-framework | `3.12.1` | 19.4x slower | 999.2μs
cerberus | `1.3.2` | 39.5x slower | 2038.5μs

Package | Version | Relative Performance | Mean serialization time
--- | --- | --- | ---
apischema | `0.14.0` |  | 29.5μs
pydantic | `1.7.3` | 1.6x slower | 48.0μs

Benchmarks were run with Python 3.8 (*CPython*) and the package versions listed above installed via *pypi* on *macOs* 11.2

!!! note
    A few precisions have to be written about these results:
    
    - *pydantic* uses *Cython* to optimize its performance but *apischema* is still a lot faster. 
    - *pydantic* benchmark is biased by the implementation of `datetime` parsing for *cattrs* (see [this post](https://stefan.sofa-rockers.org/2020/05/29/attrs-dataclasses-pydantic/) about it); in fact, if *cattrs* use a decently fast implementation, like the standard `datetime.fromisoformat`, *cattrs* becomes 3 times faster than *pydantic*, even faster than *apischema*. Of course, you don't get the same features, like complete error handling, aggregate fields, etc. In fact, performance difference between *apischema* and *cattrs* comes mostly of error handling (*cattrs* doesn't catch errors to gather them) and the gap between them is a lot reduced when playing benchmark only on valid cases.
    - *pydantic* benchmark mixes valid with invalid data (around 50/50), which doesn't correspond to real case. It means that error handling is very (too much?) important in this benchmark, and libraries like *cattrs* which raise and end simply at the first error encountered have a big advantage.
    
    
## FAQ

#### Why not ask directly for integration to *pydantic* benchmark?
[Done, but rejected](https://github.com/samuelcolvin/pydantic/pull/1525#issuecomment-630422702) because "apischema doesn't have enough usage". Let's change that!

