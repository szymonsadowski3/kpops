import logging
from enum import Enum
from typing import Annotated, Any, Literal, Sequence, Union, get_args, get_origin

from pydantic import Field, schema, schema_json_of
from pydantic.fields import ModelField
from pydantic.schema import SkipField

from kpops.cli.pipeline_config import PipelineConfig
from kpops.cli.registry import _find_classes
from kpops.components.base_components.pipeline_component import PipelineComponent


class SchemaScope(str, Enum):
    PIPELINE = "pipeline"
    CONFIG = "config"


original_field_schema = schema.field_schema


# adapted from https://github.com/tiangolo/fastapi/issues/1378#issuecomment-764966955
def field_schema(field: ModelField, **kwargs: Any) -> Any:
    if field.field_info.extra.get("hidden_from_schema"):
        raise SkipField(f"{field.name} field is being hidden")
    else:
        return original_field_schema(field, **kwargs)


schema.field_schema = field_schema

log = logging.getLogger("")


def is_valid_component(
    defined_component_types: set[str], component: type[PipelineComponent]
) -> bool:
    """
    Check whether a PipelineComponent subclass has a valid definition for the schema generation.

    :param defined_component_types: types defined so far
    :type defined_component_types: list[str]
    :param component: component type to be validated
    :type component: type[PipelineComponent]
    :return: Whether component is valid for schema generation
    :rtype: bool
    """
    component_name = component.__name__
    component_type = component.get_component_type()
    schema_type = component.__fields__.get("schema_type")
    if not schema_type:
        log.warning(f"SKIPPED {component_name}, schema_type is not defined")
        return False
    schema_type_default = schema_type.field_info.default
    if (
        get_origin(schema_type.type_) is not Literal
        or len(get_args(schema_type.type_)) != 1
    ):
        log.warning(
            f"SKIPPED {component_name}, schema_type must be a Literal with 1 argument of type str."
        )
        return False
    elif get_args(schema_type.type_)[0] != schema_type_default:
        log.warning(
            f"SKIPPED {component_name}, schema_type default value must match Literal arg"
        )
        return False
    elif schema_type_default != component_type:
        log.warning(f"SKIPPED {component_name}, schema_type != type.")
        return False
    elif schema_type_default in defined_component_types:
        log.warning(f"SKIPPED {component_name}, schema_type must be unique.")
        return False
    else:
        defined_component_types.add(schema_type_default)
        return True


def gen_pipeline_schema(
    components_module: str | None = None,
) -> None:
    """
    Generate a json schema from the models of pipeline components.

    :param components_module: Python module. Only the classes that inherit from PipelineComponent will be considered.
    :type components_module: str or None
    :rtype: None
    """

    components = tuple(_find_classes("kpops.components", PipelineComponent))
    if components_module:
        # record components types defined so far
        defined_component_types: set[str] = {
            component.__fields__["schema_type"].default
            for component in components
            if component.__fields__.get("schema_type")
        }
        custom_components = [
            component
            for component in _find_classes(components_module, PipelineComponent)
            if is_valid_component(defined_component_types, component)
        ]
        components += tuple(custom_components)

    # Create a type union that will hold the union of all component types
    PipelineComponents = Union[components]  # type: ignore[valid-type]

    AnnotatedPipelineComponents = Annotated[
        PipelineComponents, Field(discriminator="schema_type")
    ]

    schema = schema_json_of(
        Sequence[AnnotatedPipelineComponents],
        title="kpops pipeline schema",
        by_alias=True,
        indent=4,
    ).replace("schema_type", "type")
    print(schema)


def gen_config_schema() -> None:
    """
    Generate a json schema from the model of pipeline config.

    :param path: The path to the directory where the schema is to be stored.
    :type path: Path
    :rtype: None
    """
    schema = schema_json_of(PipelineConfig, title="kpops config schema", indent=4)
    print(schema)
