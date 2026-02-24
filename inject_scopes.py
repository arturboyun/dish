from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass
from enum import Enum
from contextlib import contextmanager
from contextvars import ContextVar
import inspect
from typing import Any, ParamSpec, TypeVar, get_args, get_type_hints

T = TypeVar("T")
P = ParamSpec("P")

Factory = Callable[..., Any]

# Marker type that denotes the dependency should be injected.
type Inject[Dep] = Dep


class Scope(str, Enum):
    APP = "app"  # shared across all containers (class-level cache)
    SINGLETON = "singleton"  # per-container lifetime
    TRANSIENT = "transient"  # new instance every resolve
    SESSION = "session"  # per session() block
    REQUEST = "request"  # per request() block


@dataclass
class Provider:
    factory: Factory
    scope: Scope


class Container:
    # Class-level cache shared across all Container instances (APP scope)
    _app_cache: dict[type, Any] = {}

    def __init__(self) -> None:
        # Registry: type -> provider (factory + scope)
        self._providers: dict[type, Provider] = {}
        # Cache for singleton instances
        self._singletons: dict[type, Any] = {}
        # Cache for session-scoped instances (cleared via session context)
        self._session_cache: dict[type, Any] = {}
        # Per-request cache stored in a contextvar (safe for threads/async)
        self._request_cache: ContextVar[dict[type, Any] | None] = ContextVar(
            "request_cache", default=None
        )

    def register(
        self, dep_type: type, factory: Factory, scope: Scope = Scope.TRANSIENT
    ) -> None:
        self._providers[dep_type] = Provider(factory=factory, scope=scope)

    def resolve(self, dep_type: type, stack: list[type] | None = None) -> Any:
        stack = stack or []
        if dep_type in stack:
            chain = " -> ".join(t.__name__ for t in [*stack, dep_type])
            raise RuntimeError(f"circular dependency detected: {chain}")

        provider = self._providers.get(dep_type)
        if provider is None:
            raise RuntimeError(f"factory for type {dep_type} is not registered")

        if provider.scope is Scope.APP and dep_type in Container._app_cache:
            return Container._app_cache[dep_type]

        if provider.scope is Scope.SESSION:
            if dep_type in self._session_cache:
                return self._session_cache[dep_type]

        request_cache = None
        if provider.scope is Scope.REQUEST:
            request_cache = self._request_cache.get()
            if request_cache is None:
                # Auto-start lightweight request cache if no context is set.
                request_cache = {}
                self._request_cache.set(request_cache)
            if dep_type in request_cache:
                return request_cache[dep_type]

        if provider.scope is Scope.SINGLETON and dep_type in self._singletons:
            return self._singletons[dep_type]

        target = (
            provider.factory.__init__
            if inspect.isclass(provider.factory)
            else provider.factory
        )
        annotations = get_type_hints(target, include_extras=True)
        kwargs: dict[str, Any] = {}

        for param, annotation in annotations.items():
            if param in {"self", "cls", "return"}:
                continue
            param_type = _unwrap_inject(annotation)
            kwargs[param] = self.resolve(param_type, stack=[*stack, dep_type])

        instance = provider.factory(**kwargs)

        if provider.scope is Scope.SINGLETON:
            self._singletons[dep_type] = instance
        elif provider.scope is Scope.APP:
            Container._app_cache[dep_type] = instance
        elif provider.scope is Scope.SESSION:
            self._session_cache[dep_type] = instance
        elif provider.scope is Scope.REQUEST and request_cache is not None:
            request_cache[dep_type] = instance

        return instance

    @contextmanager
    def session(self) -> Generator[Container, None, None]:
        try:
            yield self
        finally:
            self._session_cache.clear()

    @contextmanager
    def request(self) -> Generator[Container, None, None]:
        token = self._request_cache.set({})
        try:
            yield self
        finally:
            self._request_cache.reset(token)


def _unwrap_inject(annotation: Any) -> Any:
    args = get_args(annotation)
    return args[0] if args else annotation


def inject(container: Container) -> Callable[[Callable[P, T]], Callable[..., T]]:
    def decorator(func: Callable[P, T]) -> Callable[..., T]:
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            annotations = get_type_hints(func, include_extras=True)
            for param, annotation in annotations.items():
                if param == "return":
                    continue
                dep_type = _unwrap_inject(annotation)
                kwargs[param] = container.resolve(dep_type)
            return func(*args, **kwargs)

        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        wrapper.__qualname__ = func.__qualname__
        return wrapper

    return decorator


# Example usage
if __name__ == "__main__":

    class A:
        def __init__(self) -> None:
            self.n = 1

    class B:
        def __init__(self, a: Inject[A]) -> None:
            self.a = a

    class SessionCounter:
        def __init__(self) -> None:
            self.value = 0

        def inc(self) -> int:
            self.value += 1
            return self.value

    class AppSettings:
        def __init__(self) -> None:
            self.token = object()

    c = Container()
    c.register(A, A, scope=Scope.SINGLETON)
    c.register(B, B, scope=Scope.REQUEST)
    c.register(SessionCounter, SessionCounter, scope=Scope.SESSION)
    c.register(AppSettings, AppSettings, scope=Scope.APP)

    @inject(c)
    def f(x: Inject[A], y: Inject[B]) -> tuple[int, int]:
        return x.n, y.a.n

    @inject(c)
    def g(counter: Inject[SessionCounter]) -> int:
        return counter.inc()

    @inject(c)
    def b_id(b: Inject[B]) -> int:
        return id(b)

    @inject(c)
    def app_token(settings: Inject[AppSettings]) -> int:
        return id(settings.token)

    # Request scope: B будет один на запрос, но новый для каждого запроса
    with c.request():
        print(id(f()))

    with c.request():
        print(id(f()))  # новый B

    # Проверка, что B разный между запросами (id самого B, не результата f)
    with c.request():
        print(b_id())
        print(b_id())  # тот же B

    with c.request():
        print(b_id())  # новый B

    # Session scope: один инстанс на сессию, счетчик растет; при выходе из сессии сбрасывается
    with c.session():
        print(g())  # 1
        print(g())  # 2 (тот же counter)

    with c.session():
        print(g())  # снова 1 (новая сессия, новый counter)

    # APP scope: общий объект на все контейнеры
    c2 = Container()
    c2.register(AppSettings, AppSettings, scope=Scope.APP)
    print(app_token())  # id токена из c
    print(app_token())  # тот же токен
    print(c2.resolve(AppSettings).token is c.resolve(AppSettings).token)  # True
