"""Explicitly load trusted local packs into a run-scoped registry."""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from chaos_blackjack.content.ai_profile import AIProfile
from chaos_blackjack.registry import Registry, auto_load_plugins, get_registry

PACK_ROOT = Path(__file__).resolve().parents[2] / "extensions"
_ID = re.compile(r"[a-z][a-z0-9_]*\Z")


def validate_id(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError(f"Invalid content id: {value!r}; use lowercase snake_case")
    return value


@dataclass(frozen=True)
class ContentCatalog:
    registry: Registry
    starting_items: tuple[str, ...] = ()
    shop_items: tuple[str, ...] = ()
    default_ai: str = "default"


def validate_registry(registry: Registry) -> None:
    for ai_id in registry.ai_ids():
        if ai_id == "default":
            continue
        validate_id(ai_id)
        profile = registry.resolve_ai(ai_id)
        if not isinstance(profile, AIProfile) or not profile.prompt.strip() or not profile.description.strip():
            raise ValueError(f"AI {ai_id} needs an AIProfile, prompt and description")
        permissions = profile.permissions
        for key, known in (("allowed_rules", registry.rule_ids()), ("allowed_items", registry.item_ids())):
            ids = permissions.get(key, [] if key == "allowed_rules" else None)
            if ids is None and key == "allowed_items":
                continue
            if not isinstance(ids, list) or any(not isinstance(i, str) or i not in known for i in ids):
                raise ValueError(f"AI {ai_id}: {key} contains unknown ids or is not a list")
        for section, keys in (("attempt_limits", ("max_actions_per_turn", "max_active_effects")),
                              ("budget", ("chaos_budget", "charge_per_effect"))):
            values = permissions.get(section)
            if not isinstance(values, dict):
                raise ValueError(f"AI {ai_id}: missing {section} object")
            for key in keys:
                value = values.get(key)
                minimum = 1 if key == "charge_per_effect" else 0
                if type(value) is not int or value < minimum:
                    raise ValueError(f"AI {ai_id}: invalid {section}.{key}")
        backend = profile.offline_backend()
        if not callable(getattr(backend, "complete", None)):
            raise ValueError(f"AI {ai_id}: offline backend must implement complete(system, user)")


def load_content_packs(pack_ids: tuple[str, ...], *, root: Path = PACK_ROOT) -> ContentCatalog:
    auto_load_plugins()
    registry = get_registry().copy()
    starting: list[str] = []
    shop: list[str] = []
    defaults: list[str] = []
    seen: set[str] = set()
    for pack_id in pack_ids:
        validate_id(pack_id)
        if pack_id in seen:
            raise ValueError(f"Duplicate pack selection: {pack_id}")
        seen.add(pack_id)
        folder = (root / pack_id).resolve()
        if folder.parent != root.resolve():
            raise ValueError(f"Pack must be inside {root}")
        try:
            manifest = json.loads((folder / "pack.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Cannot read pack {pack_id}: {exc}") from exc
        if not isinstance(manifest, dict) or manifest.get("schema") != 1 or manifest.get("id") != pack_id:
            raise ValueError(f"Pack {pack_id}: expected schema 1 and matching id")
        before = set(registry.item_ids())
        module_name = f"_chaos_blackjack_pack_{pack_id}"
        spec = importlib.util.spec_from_file_location(module_name, folder / "plugin.py")
        if spec is None or spec.loader is None:
            raise ValueError(f"Pack {pack_id}: missing plugin.py")
        module = importlib.util.module_from_spec(spec)
        previous = sys.modules.get(module_name)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
            register = getattr(module, "register", None)
            if not callable(register):
                raise ValueError("plugin.py must define register(registry)")
            register(registry)
        except Exception as exc:
            if previous is None:
                sys.modules.pop(module_name, None)
            else:
                sys.modules[module_name] = previous
            raise ValueError(f"Pack {pack_id}: {exc}") from exc
        for item_id in set(registry.item_ids()) - before:
            validate_id(item_id)
            cls = registry.resolve_item(item_id)
            if getattr(cls, "name", None) != item_id or not callable(getattr(cls, "use", None)):
                raise ValueError(f"Item {item_id}: expected matching name and use(ctx)")
            if not registry.describe_item(item_id).strip():
                raise ValueError(f"Item {item_id}: register a nonempty description")
        if "reward_items" in manifest:
            raise ValueError(f"Pack {pack_id}: replace reward_items with shop_items and balance-profile shop prices")
        for key, output in (("starting_items", starting), ("shop_items", shop)):
            ids = manifest.get(key, [])
            if not isinstance(ids, list) or any(not isinstance(i, str) or i not in registry.item_ids() for i in ids):
                raise ValueError(f"Pack {pack_id}: {key} contains unknown item ids or is not a list")
            output.extend(ids)
        default_ai = manifest.get("default_ai")
        if default_ai is not None:
            if not isinstance(default_ai, str) or default_ai not in registry.ai_ids():
                raise ValueError(f"Pack {pack_id}: unknown default_ai")
            defaults.append(default_ai)
    validate_registry(registry)
    # Explicit --ai is required if several packs have different defaults.
    default = defaults[0] if defaults and len(set(defaults)) == 1 else "default"
    return ContentCatalog(registry, tuple(starting), tuple(dict.fromkeys(shop)), default)
