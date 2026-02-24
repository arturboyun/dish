from collections.abc import Callable
from functools import wraps
import inspect
from typing import Any, ParamSpec, TypeVar, get_args, get_type_hints

T = TypeVar("T")
P = ParamSpec("P")

Factory = Callable[..., Any]

type Inject[Dep] = Dep

Dep = TypeVar("Dep")

max_recursion_depth = 10


def _resolve_annotation_type(annotation: Any) -> Any:
    annotation_args = get_args(annotation)
    print(f"{annotation=}")
    print(f"{annotation_args=}")
    if annotation_args:
        return annotation_args[0]
    return annotation


def _resolve_factory_dependencies(
    param_type: type,
    dependencies: dict[type, Factory],
    max_recursion_depth: int = 10,
) -> Any:
    factory = dependencies[param_type]
    if max_recursion_depth <= 0:
        raise RuntimeError("maximum recursion depth exceeded")

    target = factory.__init__ if inspect.isclass(factory) else factory
    factory_annotations = get_type_hints(target)
    factory_required_injections = factory_annotations.keys()
    factory_kwargs = {}
    for factory_param in factory_required_injections:
        if factory_param in ("return", "self", "cls"):
            continue

        factory_param_type = _resolve_annotation_type(
            factory_annotations[factory_param]
        )
        if factory_param_type not in dependencies.keys():
            raise RuntimeError(
                f"factory for type {factory_param_type} is not registered"
            )

        factory_kwargs[factory_param] = _resolve_factory_dependencies(
            factory_param_type, dependencies, max_recursion_depth - 1
        )

    return factory(**factory_kwargs)


def inject(
    dependencies: dict[type, Factory],
) -> Callable[[Callable[P, T]], Callable[..., T]]:
    def decorator(func: Callable[P, T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            annotations = get_type_hints(func)
            required_injections = annotations.keys()

            print(f"{annotations=}")
            print(f"{required_injections=}")

            for param in required_injections:
                if param == "return":
                    continue

                param_type = _resolve_annotation_type(annotations[param])
                if param_type not in dependencies.keys():
                    raise RuntimeError(
                        f"factory for type {param_type} is not registered"
                    )

                print(f"{param=}")
                print(f"{param_type=}")

                kwargs[param] = _resolve_factory_dependencies(
                    param_type, dependencies, max_recursion_depth
                )

            return func(*args, **kwargs)

        return wrapper

    return decorator
