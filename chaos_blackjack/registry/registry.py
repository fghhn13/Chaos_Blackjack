"""Central registry — plugins register here; core never imports plugin modules."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

from chaos_blackjack.contracts.items import ItemProtocol
from chaos_blackjack.rules.modifiers import RuleModifier

T = TypeVar("T")

ChaosRuleFactory = Callable[[dict[str, Any]], RuleModifier]


class Registry:
    def __init__(self) -> None:
        self._items: dict[str, type[ItemProtocol]] = {}
        self._chaos_rules: dict[str, ChaosRuleFactory | type[Any]] = {}

    def register_item(self, name: str, cls: type[ItemProtocol]) -> None:
        self._items[name] = cls

    def register_rule(self, name: str, factory: ChaosRuleFactory | type[Any]) -> None:
        """Register either a ChaosRulePlugin class with from_params or a callable(params)->RuleModifier."""
        self._chaos_rules[name] = factory

    def resolve_item(self, name: str) -> type[ItemProtocol] | None:
        return self._items.get(name)

    def build_chaos_rule(self, name: str, params: dict[str, Any] | None = None) -> RuleModifier | None:
        p = params or {}
        factory = self._chaos_rules.get(name)
        if factory is None:
            return None
        if isinstance(factory, type):
            from_params = getattr(factory, "from_params", None)
            if callable(from_params):
                return from_params(p)
            return None
        return factory(p)


_GLOBAL: Registry | None = None


def get_registry() -> Registry:
    global _GLOBAL
    if _GLOBAL is None:
        _GLOBAL = Registry()
    return _GLOBAL


def register_item(name: str, cls: type[ItemProtocol]) -> None:
    get_registry().register_item(name, cls)


def register_rule(name: str, factory: ChaosRuleFactory | type[Any]) -> None:
    get_registry().register_rule(name, factory)
