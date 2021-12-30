from typing import Sequence, Union


class TypeCheckError(TypeError):
    def __init__(self, msg: str, loc: Sequence[Union[int, str]]):
        self.msg = msg
        self.loc = loc

    def __str__(self):
        return f"{list(self.loc)} {self.msg}"
