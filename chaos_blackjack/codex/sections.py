"""The collection grouped by series (docs/design/CODEX.md, "Sections").

`codex_sections(config)` returns the **Classic Table** (the core series)
first, then one section per dealer (an expansion, see
`chaos_blackjack.modes.register_series`):

* Classic Table: its tables, the items sold at every table (or at none), Chaos
  rules no dealer uses, and guest Chaos AIs from content packs.
* A dealer (e.g. Poker Head): the character's portrait, name, profile and
  signature line, then the Chaos rules its tables may apply and the items
  only its tables sell. How the AI works is not shown here; the table's
  numbers are on the mode's detail page.

Nothing is left out: every rule, item, mode and pack AI appears in some
section. Headless; the GUI only lays the sections out.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from chaos_blackjack.app.config import RunConfig
from chaos_blackjack.codex.models import CodexEntry
from chaos_blackjack.codex.registry import codex_entries


@dataclass(frozen=True)
class CodexGroup:
    id: str
    label: str
    entries: tuple[CodexEntry, ...]
    empty: str = ""                     # shown instead of tiles when there are none


@dataclass(frozen=True)
class CodexSection:
    id: str                             # "core" or an expansion's series id
    label: str                          # tab label
    groups: tuple[CodexGroup, ...]
    expansion: bool = False
    host: str | None = None             # an expansion's host
    mode: CodexEntry | None = None      # an expansion's (first) table
    portrait: str = ""                  # asset id
    summary: str = ""
    quote: str = ""                     # the dealer's signature line
    profile: tuple[str, ...] = ()       # the dealer's character profile (paragraphs)
    entries: tuple[CodexEntry, ...] = field(default=())   # every entry, in display order

    def __post_init__(self) -> None:
        if not self.entries:
            object.__setattr__(self, "entries", tuple(e for g in self.groups for e in g.entries))


def rule_pool(config: RunConfig, rule_ids: list[str]) -> list[str]:
    """Rules a table with this config may apply."""
    if not config.enable_chaos:
        return []
    allowed = [r for r in rule_ids if r not in config.disabled_rules]
    if config.rule_pool is not None:
        allowed = [r for r in allowed if r in config.rule_pool]
    return allowed


def _host_look(host: str) -> tuple[str, str, tuple[str, ...], str]:
    """(name, portrait asset id, profile, signature line) of a bundled host."""
    from chaos_blackjack.content.builtin_persona import HOST_NAMES, host_persona
    from chaos_blackjack.content.host_script import host_profile

    profile, signature = host_profile(host)
    name = HOST_NAMES.get(host, host.replace("_", " ").title())
    return name, host_persona(host).asset_id("welcome"), profile, signature


def codex_sections(config: RunConfig | None = None) -> list[CodexSection]:
    from chaos_blackjack.modes import modes, series_list, sold_items

    cfg = config if config is not None else RunConfig()
    rules = codex_entries("rule", cfg)
    items = codex_entries("item", cfg)
    mode_entries = {e.id: e for e in codex_entries("mode", cfg)}
    ais = [e for e in codex_entries("ai", cfg) if e.id != "default"]
    tables = [(m, m.apply(cfg)) for m in modes()]

    # Only items count here: a table's own offers (J-54's contracts) are not items,
    # and a table that sells no items does not make the others' items table-specific.
    item_ids = {e.id for e in items}
    stocked = [s for s in (sold_items(c) & item_ids for _, c in tables) if s]
    everywhere = set.intersection(*stocked) if stocked else set()
    anywhere = set.union(*stocked) if stocked else set()
    rule_ids = [e.id for e in rules]

    def pools(series_id: str) -> tuple[list, set[str], set[str]]:
        own = [(m, c) for m, c in tables if m.series == series_id]
        used = {r for _, c in own for r in rule_pool(c, rule_ids)}
        sold = {i for _, c in own for i in sold_items(c)} - everywhere
        return own, used, sold

    expansions: list[CodexSection] = []
    claimed_rules: set[str] = set()
    for series in series_list():
        if not series.expansion:
            continue
        own, used, sold = pools(series.id)
        if not own:
            continue
        sells_items = any(i in item_ids for _, c in own for i in sold_items(c))
        claimed_rules |= used
        first = own[0][0]
        host, portrait, profile, signature = _host_look(first.host)
        groups = [
            CodexGroup("rules", "Chaos rules", tuple(e for e in rules if e.id in used),
                       empty=f"{host} never bends the rules here."),
            CodexGroup("items", "Table items", tuple(e for e in items if e.id in sold),
                       empty="Only the Classic Table's items are sold here." if sells_items
                       else "No items are sold here."),
        ]
        if len(own) > 1:
            groups.insert(0, CodexGroup("tables", "Tables", tuple(mode_entries[m.id] for m, _ in own
                                                                  if m.id in mode_entries)))
        expansions.append(CodexSection(series.id, series.name, tuple(groups), expansion=True, host=first.host,
                                       mode=mode_entries.get(first.id), portrait=portrait,
                                       summary=first.description, quote=signature, profile=profile))

    core_tables = tuple(mode_entries[m.id] for m, _ in tables if m.series == "core" and m.id in mode_entries)
    _, core_rules, core_items = pools("core")
    groups = [
        CodexGroup("tables", "Tables", core_tables, empty="No tables yet."),
        CodexGroup("items", "Items", tuple(e for e in items
                                           if e.id in everywhere or e.id in core_items or e.id not in anywhere),
                   empty="No items are sold at every table."),
    ]
    spare = tuple(e for e in rules if e.id in core_rules or e.id not in claimed_rules)
    if spare:
        groups.append(CodexGroup("rules", "Chaos rules", spare))
    if ais:
        groups.append(CodexGroup("ai", "Guest Chaos AIs", tuple(ais)))
    from chaos_blackjack.modes import get_series

    core = CodexSection("core", get_series("core").name, tuple(groups),
                        summary="The classic table and the items every table sells.")
    return [core, *expansions]
