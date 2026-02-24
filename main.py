import inspect
from typing import Any, Callable

from inject import Inject, inject


class A:
    def print(self) -> None:
        print("AAAAAAAAAAAAAAAAAAAAAAAAAAA\n")


class B:
    def __init__(self, a: Inject[A]) -> None:
        self.a = a

    def print(self) -> None:
        print("B")
        self.a.print()


class C:
    def __init__(self, b: B) -> None:
        self.b = b

    def print(self) -> None:
        print("C")
        self.b.print()


def create_c(b: B) -> C:
    return C(b)


dependencies: dict[type, Callable[..., Any]] = {
    A: lambda: A(),
    B: B,
    C: create_c,
}


@inject(dependencies)
def print_a(a: Inject[A]) -> None:
    a.print()


@inject(dependencies)
def print_b(b: Inject[B]) -> None:
    b.print()


@inject(dependencies)
def print_c(c: Inject[C]) -> None:
    c.print()


print(f"signature={inspect.signature(print_a)}")

print_a()
print_b()
print_c()
