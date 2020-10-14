# flake8: noqa
# type: ignore
from typing import *


class Wrapper:
    def __init__(self, cls):
        self.cls = cls
        self.implem = cls.__origin__ or cls.__extra__  # extra in 3.6

    def __getitem__(self, item):
        return self.cls[item]

    def __call__(self, *args, **kwargs):
        return self.implem(*args, **kwargs)


for cls in (Dict, List, Set, FrozenSet, Tuple, Type):  # noqa
    wrapper = Wrapper(cls)
    globals()[wrapper.implem.__name__] = wrapper

Set = AbstractSet  # type: ignore
