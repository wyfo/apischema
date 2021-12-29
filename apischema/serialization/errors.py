from typing import Sequence, Union


class TypeCheckError(TypeError):
    def __init__(self, msg: str, path: Sequence[Union[int, str]]):
        self.msg = msg
        self.path = path

    def __str__(self):
        return f"{list(self.path)} {self.msg}"
