import json
from typing import Any, TypeVar

from pydantic import BaseModel as PydanticBaseModel
from pydantic import ConfigDict, model_validator

T = TypeVar("T", bound="BaseModel")


class BaseModel(PydanticBaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    @classmethod
    def from_model(cls: type[T], model: T | None = None) -> T | None:
        if not model:
            return None
        return cls.model_validate(model)

    @classmethod
    def from_dict(cls: type[T], obj: dict[str, Any] | None = None) -> T | None:
        if not obj:
            return None
        return cls.model_validate(obj)

    @classmethod
    def from_json(cls: type[T], json_str: str | None = None) -> T | None:
        if not json_str:
            return None
        return cls.model_validate_json(json_str)

    def to_json(self, *args, **kwargs) -> str:
        return self.model_dump_json(*args, **kwargs)

    def to_dict(self, *args, **kwargs) -> dict[str, Any]:
        return self.model_dump(*args, **kwargs)

    @model_validator(mode="before")
    @classmethod
    def validate_to_json(cls, value):
        if isinstance(value, str):
            return cls(**json.loads(value))
        return value
