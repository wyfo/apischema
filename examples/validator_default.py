from dataclasses import dataclass, field

from apischema import deserialize, validator

validator_run = False


@dataclass
class Foo:
    bar: int = field(default=0)

    @validator(bar)
    def password_match(self):
        global validator_run
        validator_run = True
        if self.bar < 0:
            raise ValueError("negative")


deserialize(Foo, {})
assert not validator_run
