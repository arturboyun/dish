from functools import wraps
import inspect
from typing import Any, TypeVar, Callable, ParamSpec


class A:
    def print(self) -> None:
        print("A")


class B:
    def __init__(self, a: A) -> None:
        self.a = a

    def print(self) -> None:
        print("B")
        self.a.print()


class C:
    def print(self) -> None:
        print("C")


def get_b(a: A) -> B:
    return B(a)


dependencies: dict[type, Callable[..., Any]] = {
    A: lambda: A(),
    B: get_b,
    C: lambda: C(),
}

T = TypeVar("T")
P = ParamSpec("P")


def inject() -> Callable[[Callable[P, T]], Callable[..., T]]:
    def decorator(func: Callable[P, T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            annotations = func.__annotations__
            required_injections = annotations.keys()

            print(f"{annotations=}")
            print(f"{required_injections=}")

            for param in required_injections:
                if param == "return":
                    continue
                param_type = annotations[param]
                if param_type not in dependencies.keys():
                    raise RuntimeError(
                        f"factory for type {param_type} is not registered"
                    )
                print(f"{param=}")

                factory = dependencies[param_type]
                factory_annotations = factory.__annotations__
                factory_params = factory_annotations.keys()
                factory_kwargs: dict[str, Any] = {}

                print(f"{factory_annotations=}")
                print(f"{factory_params=}")

                for factory_param in factory_params:
                    if factory_param == "return":
                        continue
                    factory_param_type = factory_annotations[factory_param]
                    if factory_param_type not in dependencies.keys():
                        raise RuntimeError(
                            f"factory for type {factory_param_type} is not registered"
                        )
                    factory_kwargs[factory_param] = dependencies[factory_param_type]()
                kwargs[param] = factory(**factory_kwargs)

            return func(*args, **kwargs)

        return wrapper

    return decorator


@inject()
def print_a(a: C) -> None:
    a.print()


def test_get_b() -> None:
    @inject()
    def get_b(b: B) -> None:
        print(b)

    get_b()


print(f"signature={inspect.signature(print_a)}")
print_a()
