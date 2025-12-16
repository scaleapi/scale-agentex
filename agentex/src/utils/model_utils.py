import json
from typing import Any, TypeVar, get_args, get_origin

from pydantic import BaseModel as PydanticBaseModel
from pydantic import ConfigDict, Field, create_model, model_validator

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


def make_optional(
    entity_model: type[BaseModel], model_name_suffix: str = "Optional"
) -> type[BaseModel]:
    """
    Create a new model with all fields made optional (| None with default=None).

    Args:
        entity_model: The source entity model to make optional
        model_name_suffix: Suffix for the generated model name (defaults to "Filter")

    Returns:
        A new Pydantic model class with all fields made optional

    Example:
        TaskMessageFilter = make_optional(TaskMessageEntity)
        UserFilter = make_optional(UserEntity)
    """
    fields = {}
    for field_name, field_info in entity_model.model_fields.items():
        # Get the original type annotation
        original_type = field_info.annotation

        # Check if already optional (Union with None)
        if get_origin(original_type) is not None:
            args = get_args(original_type)
            if type(None) in args:
                # Already optional, keep as is
                optional_type = original_type
            else:
                # Make it optional by adding | None
                optional_type = original_type | None
        else:
            # Make it optional by adding | None
            optional_type = original_type | None

        # Create new field with optional type and default=None
        new_field = Field(
            default=None,
            description=field_info.description,
        )

        fields[field_name] = (optional_type, new_field)

    filter_model_name = f"{entity_model.__name__}{model_name_suffix}"
    return create_model(filter_model_name, __base__=BaseModel, **fields)
