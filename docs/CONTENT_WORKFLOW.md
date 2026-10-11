# Item and Chaos AI content workflow

Local content packs are the standard way to add items and Chaos AI personalities.
One folder can be copied into `extensions/`, validated, and selected at launch.
Existing games keep their original content unless a pack is selected. Pack
registrations belong to a controller, not the process-wide built-in registry.

## Quick start

The repository includes the `example` pack:

```bash
python -m chaos_blackjack.content validate example
python -m chaos_blackjack.content play example
```

The second command opens the GUI directly at the table, with the pack's starting
item, balance-profile shop offers and default AI. Press **I** on your turn to browse every item,
read its help, and use it with **Enter**.
GUI playback requires the optional dependency: `pip install -e ".[gui]"`.

For JSON command play without Pygame:

```bash
python -m chaos_blackjack.content play example --agent --seed 7
```

Enter one JSON command per line, such as `{"cmd":"bet","amount":10}`,
`{"cmd":"act","action":"hit"}`, or `{"cmd":"quit"}`. `play --agent` is an
in-memory stream. For separate calls with persistent state:

```bash
python -m chaos_blackjack.agent new --pack example --ai example_dealer --chaos --seed 7
python -m chaos_blackjack.agent bet 10
python -m chaos_blackjack.agent act use_item example_trim
```

The trim item needs at least three cards, so use it after a non-busting hit.

## Standard creation process

1. Describe the behavior before coding. For an item, specify when it succeeds,
   which state changes, what failure means, and how it is obtained. For an AI,
   specify what it can observe, which actions it prefers, and which actions and
   budgets it is allowed. Decide whether this is an item effect, an AI decision,
   or a new game rule: a personality cannot create mechanics by prompting alone.
2. Generate a pack with a unique lowercase snake_case id:

   ```bash
   python -m chaos_blackjack.content init lucky
   ```

3. Edit the generated item, effect and offline AI in `extensions/lucky/plugin.py`.
   Edit `prompt.txt` for the model personality and `permissions.json` for the hard
   limits. Edit `pack.json` for acquisition and the shortcut's default AI.
4. Adapt `test_lucky.py` to assert your actual behavior. Include success, failure
   without consumption, and the final state after the effect. AI tests should
   cover valid decisions and boundary cases such as an empty inventory.
5. Run the contract check, the pack's behavior tests, and the repository tests:

   ```bash
   python -m chaos_blackjack.content validate lucky
   python -m pytest extensions/lucky/test_lucky.py
   python -m pytest
   ```

6. Launch the pack:

   ```bash
   python -m chaos_blackjack.data clone default lucky
   python -m chaos_blackjack.content install-shop lucky --profile lucky
   python -m chaos_blackjack.content play lucky --profile lucky
   ```

`init` creates a working example, not an empty placeholder. It refuses to
overwrite an existing folder. Normal tests use the bundled stub or pack's offline
backend; they must never call a billed model.

## Pack layout and activation

```text
extensions/lucky/
  pack.json           # identity, starting/shop items, default AI
  plugin.py           # register(registry), items, effects, offline backend
  permissions.json    # AI allowed ids, attempt limits and budget
  shop.sql            # shop_item rows with prices, installed into a balance profile
  prompt.txt          # real model instructions
  test_lucky.py       # behavioral tests, run explicitly
```

The loader requires `pack.json` and `plugin.py`. Other files are read by the pack
and may be organized differently as it grows. The generated manifest is:

```json
{
  "schema": 1,
  "id": "lucky",
  "starting_items": ["lucky_trim"],
  "shop_items": ["lucky_trim"],
  "default_ai": "lucky_dealer"
}
```

- `starting_items` adds copies to the player's inventory at the start of a run.
  Repeating an id grants several copies.
- `shop_items` lists items intended for the shop. Prices are `shop_item` rows in
  the selected balance profile; the manifest never overrides those numbers.
  Install a generated pack's `shop.sql` into a cloned, editable profile with
  `content install-shop`. The bundled example already has a shipped 20-chip row.
  Tune prices with `data set <profile> item.<id>.price <value>`. Registration
  alone does not grant items, and win streaks no longer grant pack rewards.
  Old `reward_items` manifests are rejected with migration instructions.
- `default_ai` is used by `content play`. Direct GUI and Agent commands require
  `--ai` to select a custom AI.
- Packs can contain only items or only AIs: omit unused registrations and omit
  `default_ai`, `starting_items` or `shop_items` as appropriate.
- Id collisions fail rather than silently replacing built-ins or another pack.
  Prefix item and AI ids with the pack id to avoid collisions.

Useful commands:

```bash
python -m chaos_blackjack.content list
python -m chaos_blackjack.content inspect lucky
python -m chaos_blackjack.content validate lucky another_pack
python -m chaos_blackjack.content play lucky another_pack --ai lucky_dealer
python -m chaos_blackjack.gui --pack lucky --ai lucky_dealer --chaos
```

When selected packs have different default AIs, the shortcut uses `default` unless
`--ai` is supplied. The direct entrypoints accept repeated `--pack` flags. Pack
Python code is trusted local application code, not an isolated executable
sandbox; only the AI's structured actions are permission checked. Copy reviewed
packs into `extensions/` and restart a game after editing them. F5 refreshes art,
not Python behavior. Optional `<item_id>.png` files in `assets/` provide icons;
unknown ids use a generic fallback image without requiring a manifest edit when
rendered by the asset manager. The inventory overlay works without icons.

## Item contract

Implement `name` and `use(ctx) -> ItemResult`, then register through the supplied
registry. Do not call the global registration helpers from a content pack:

```python
def register(registry):
    registry.register_item(
        TrimHand.name, TrimHand,
        description="Discard your last card when you have at least three cards.",
    )
```

`ItemContext` provides the immutable current `GameState`, an event emitter and a
next-card rank callback. Return `ok=False` for unmet conditions. Return
`ok=True` with a message for an information item. For a state-changing item,
return effects implementing `apply(state) -> GameState`:

```python
@dataclass(frozen=True)
class RemoveLastCard:
    def apply(self, state):
        return state.with_player_hand(state.player_hand[:-1])

# Inside use(), after checking at least three cards:
return ItemResult(ok=True, message="Your last card was discarded.",
                  effects=(RemoveLastCard(),))
```

The executor applies effects in order, then consumes one copy on success. It
publishes collected events after success. Player and AI item use share this
executor. The AI path also charges the configured chaos budget. New effects do
not need an entry in `app/item_use.py`; `extra` remains supported for the existing
Swap implementation only. Description metadata goes into both Agent observations
and GUI help automatically.

Effects currently transform round state: hands, deck and inventory. They should
not consume their own item copy; the executor owns consumption. Run money,
betting rules, active modifiers, timed effects and new turn phases require
additional explicit game contracts. `use_item` is available during the player
turn. Items cannot rescue a hand after a hit has already ended the round.

## Chaos AI contract

An `AIProfile` bundles description, prompt, permissions and a factory that returns
a fresh offline `LLMBackend`. Register it with `registry.register_ai(id, profile)`.
The factory's backend implements:

```python
def complete(self, system_prompt: str, user_prompt: str) -> str:
    obs = json.loads(user_prompt)
    return json.dumps({"action": "noop", "narration": "Your move."})
```

Both an offline backend and a real model receive the same schema-1 JSON input:

| Field | Meaning |
| --- | --- |
| `player_cards` | Visible rank/suit objects |
| `dealer_up_card` | First dealer card, or null |
| `deck_remaining` | Count; never deck order |
| `chaos_budget_remaining` | Budget left this round |
| `chaos_actions_this_turn` | Successful actions charged this round |
| `inventory` | Shared player inventory ids |
| `active_rules` | Active rule ids |
| `allowed_rules`, `allowed_items` | Permission ids; null items means unrestricted |

The backend returns one JSON object using the existing verbs `noop`, `apply_rule`
or `use_item`. The pipeline parses, permission checks and resolves it through the
scoped registry. Offline decision code cannot bypass these checks. Avoid hidden
backend memory: Agent commands recreate the backend between processes, so a
stateless deterministic strategy is the standard resumable implementation.

The generated permissions explicitly list allowed rules and items, with
`attempt_limits.max_actions_per_turn`, `attempt_limits.max_active_effects`,
`budget.chaos_budget` and `budget.charge_per_effect`. The loader rejects unknown
ids, malformed limits and duplicates. `validate` also exercises each item and
each custom offline AI on a sample table. This is a smoke check; pack-specific
tests must verify the intended gameplay.

Switch a profile to the configured real relay explicitly:

```bash
python -m chaos_blackjack.content play lucky --llm
```

This uses the same prompt, permissions and executor while replacing the offline
backend. It makes billed calls during play; validation never constructs the relay.
Credentials stay in `.env`. The original built-in controller/GUI environment
opt-in remains supported; pack AIs default to their offline backend.

### Persona: portraits and table lines

`AIProfile(persona=Persona(...))` gives an AI its own look and voice at the
table. It is presentation only and never widens what the AI may do.

```python
from chaos_blackjack.content.ai_profile import Persona

Persona(
    id="lucky",                       # portrait asset ids become lucky_<expression>
    name="Lucky",                     # shown on the Chaos panel and in the codex
    portraits={"neutral": folder / "portraits/neutral.png", "grin": ...},
    moods={"rule_applied": "grin", "outcome_player": "neutral"},     # event -> expression
    lines={"rule_applied": ("{rule}, if you please.",), "idle": ("Well?",)},  # rotated
    default="neutral",
)
```

Events are listed in `PERSONA_EVENTS` (`idle`, `off`, `round_started`,
`rule_applied`, `narration`, `poke`, `item_used`, `player_bust`,
`player_blackjack`, `dealer_blackjack`, `dealer_busts` and `outcome_<result>`).
An event without a mood keeps the current expression; one without lines keeps
the current speech, and the backend's narration and advice always win. The
portraits are found by the GUI's asset manager after its own asset folders; the
codex uses the persona's name and default portrait. AIs without a persona keep
the built-in Chaos AI look.

Portrait advice: when the player pokes the portrait, a pack AI's offline backend
receives the poke prompt with `{"intent": "guide" | "mislead", "context": {...}}`
and must answer `{"reply": "one or two sentences"}`.

The `poker_head` pack is a complete example: eight portraits, persona lines,
weighted offline rules with narration, and in-character advice.

These profiles control the **Chaos AI**, not an automated player or the normal
dealer draw policy. The controller currently invokes chaos once before the
player turn. Increasing permission limits alone does not add invocation points.
New action verbs or call timings require a deliberate core change.

## Saves and compatibility

Controller saves and Agent state persist selected pack ids, AI id and run
configuration. Loading recreates the registry before restoring modifiers and
inventory. Keep the same pack folders and ids available to resume; missing packs
fail with a clear error. Editing pack code changes resumed behavior, so retain the
same files for reproducible runs. Mutable offline-backend state is not serialized.

The older `cli/main.py` text session still has its own flow and does not expose
pack selection. Use the GUI, JSON Agent CLI, or Python controller API:

```python
controller = GameController(RunConfig(
    content_packs=("lucky",), ai_id="lucky_dealer", enable_chaos=True, use_llm=False,
))
```
