from functools import wraps
import inspect
from typing import Any, TypeVar, Callable, ParamSpec


class A:
    def print(self) -> None:
        print("A")


class B: ...


dependencies: dict[str, Callable[..., Any]] = {
    "a": lambda: A(),
    "b": lambda: B(),
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
                if param not in dependencies.keys():
                    raise RuntimeError(f"canno't resolve param {param}")
                print(f"{param=}")
                kwargs[param] = dependencies[param]()
            return func(*args, **kwargs)

        # sig = inspect.signature(func)
        # sig = sig.replace(parameters=tuple(sig.parameters.values())[1:])
        # wrapper.__signature__ = sig

        return wrapper

    return decorator


@inject()
def print_a(a: A) -> None:
    a.print()


def test_get_b() -> None:
    @inject()
    def get_b(b: B) -> None:
        print(b)


print(f"signature={inspect.signature(print_a)}")
print_a()
