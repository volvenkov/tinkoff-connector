from enum import Enum


class BaseEnum(str, Enum):
    @classmethod
    def value_of(cls, value):
        for k, v in cls.__members__.items():
            if k == value or v == value:
                return v
        else:
            raise ValueError(f"{cls.__name__} enum not found for {value}")

