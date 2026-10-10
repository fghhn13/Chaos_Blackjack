# 🃏 Chaos Blackjack — CLI Interaction Spec (User-Facing UX)

---

## 🎯 Design goals

This CLI is not a "bare-bones interface". It is:

> **A readable, controllable, explainable turn-based interaction system**

Core requirements:

* ✅ State Visibility
* ✅ Action Clarity
* ✅ Feedback Transparency
* ✅ Explainable Chaos

---

## 🧠 Turn structure (standard template)

Every turn must follow this order exactly:

```text
[HEADER]
[GAME STATE]
[CHAOS EFFECTS]
[ITEMS]
[ACTIONS]
[COMMANDS]
[INPUT]
[RESULT / FEEDBACK]
```

---

## 🧩 1. Header (visual anchor)

```text
==============================
🃏 Chaos Blackjack
==============================
Turn: 3
```

---

## 🧩 2. Game State (core information)

```text
Your Hand:
  [7♠, 9♦]  → Total: 16

Dealer:
  [6♣, ?]
```

👉 Rules:

* Must be aligned
* Must show the total
* Must distinguish visible from hidden information

---

## 🧩 3. Chaos Effects (AI behaviour)

```text
------------------------------
🤖 Chaos AI Active:
"You look too comfortable..."

⚡ Active Effects:
- All 10 cards are worth 8 (this turn)
- Bust converts to half score
------------------------------
```

👉 Rules:

* AI behaviour must be shown explicitly
* Effects must be listed
* Duration must be stated (e.g. "this turn")

---

## 🧩 4. Items (player resources)

```text
🎒 Items:
  1. Peek (1 use)
  2. Shield (1 use)
```

👉 Rules:

* Show remaining uses
* Number items in order

---

## 🧩 5. Actions (main moves)

```text
Available Actions:
  1. Hit
  2. Stand
  3. Use Item
```

👉 Generated dynamically (the AI can affect them)

For example:

```text
⚡ Effect: Forced Hit

Available Actions:
  1. Hit
```

---

## 🧩 6. Commands (auxiliary)

```text
Commands:
  info   → show current rules
  ai     → show the AI's explanation
  items  → show item details
  debug  → (dev only)
  quit   → exit the game
```

---

## 🧩 7. Input (single entry point)

```text
> 
```

### Accepted input

| Input     | Meaning          |
| --------- | ---------------- |
| 1 / hit   | Hit              |
| 2 / stand | Stand            |
| 3         | Use Item         |
| info      | Show rules       |
| ai        | AI explanation   |
| quit      | Exit             |

---

## 🧩 8. Sub-menu (Use Item)

```text
Choose Item:
  1. Peek
  2. Shield

> 
```

---

## 🔁 9. Feedback phase (must be explicit)

### Player action feedback

```text
You draw: 10♥
```

### Chaos feedback

```text
⚡ Chaos Effect Triggered:
10 → 8
```

### State change

```text
New Total: 24
```

### Result

```text
💀 BUST!
```

---

## 🤖 AI explanation system (optional, strongly recommended)

```text
> ai

🤖 Chaos AI:
"You rely too much on high-value cards."
```

---

## 📊 `info` command (rules made visible)

```text
> info

Current Rules:
- Card Value: modified (10 → 8)
- Bust Rule: modified (half penalty)
```

---

## 🧪 Debug mode (development)

```text
> debug state
> debug rules
```

---

## ⚠️ UX constraints (mandatory)

### ❌ Never

* Free-form, unconstrained text input
* Hidden AI behaviour
* Rule changes that are not shown
* Vague feedback (e.g. "something happened")

---

### ✅ Always

* Every change is visible
* Every action is explainable
* Every input is constrained

---

## 🎯 Key experience goals

Every turn the player must clearly know:

1. What state am I in?
2. Did the rules change?
3. What can I do?
4. What did the AI just do?
