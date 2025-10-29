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

    @model_validator(mode="before")
    @classmethod
    def extract_sqlalchemy_relationships(cls, data: Any) -> Any:
        """
        Extract loaded SQLAlchemy relationships from ORM objects.

        This validator handles SQLAlchemy ORM objects by extracting both:
        - Column values
        - Loaded relationships

        For non-ORM objects, it passes the data through unchanged.
        """
        # Check if this is a SQLAlchemy ORM object
        if not hasattr(data, "__table__"):
            return data

        try:
            from sqlalchemy import inspect as sqlalchemy_inspect
        except ImportError:
            return data

        inst = sqlalchemy_inspect(data)
        result = {}

        # Extract column values
        for column_key in inst.mapper.columns.keys():
            result[column_key] = getattr(data, column_key)

        for rel_attr in inst.mapper.relationships:
            if rel_attr.key not in inst.unloaded:
                result[rel_attr.key] = getattr(data, rel_attr.key)

        return result

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
