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
        self._item_help: dict[str, str] = {}
        self._ais: dict[str, Any] = {}

    def register_item(self, name: str, cls: type[ItemProtocol], *, description: str = "") -> None:
        if name in self._items:
            raise ValueError(f"Duplicate item id: {name}")
        self._items[name] = cls
        self._item_help[name] = description or str(getattr(cls, "description", ""))

    def register_rule(self, name: str, factory: ChaosRuleFactory | type[Any]) -> None:
        """Register either a ChaosRulePlugin class with from_params or a callable(params)->RuleModifier."""
        if name in self._chaos_rules:
            raise ValueError(f"Duplicate rule id: {name}")
        self._chaos_rules[name] = factory

    def register_ai(self, name: str, profile: Any) -> None:
        if name == "default" or name in self._ais:
            raise ValueError(f"Duplicate or reserved AI id: {name}")
        self._ais[name] = profile

    def resolve_ai(self, name: str) -> Any | None:
        return self._ais.get(name)

    def describe_item(self, name: str) -> str:
        return self._item_help.get(name, "")

    def item_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._items))

    def rule_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._chaos_rules))

    def ai_ids(self) -> tuple[str, ...]:
        return ("default", *sorted(self._ais))

    def copy(self) -> Registry:
        """Keep pack registrations local to one controller / validation run."""
        registry = Registry()
        registry._items = self._items.copy()
        registry._chaos_rules = self._chaos_rules.copy()
        registry._item_help = self._item_help.copy()
        registry._ais = self._ais.copy()
        return registry

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
