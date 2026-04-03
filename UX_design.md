# 🃏 Chaos Blackjack — CLI 交互设计规范（User-Facing UX）

---

## 🎯 设计目标

本CLI不是“简陋界面”，而是一个：

> **可读、可控、可解释的回合式交互系统**

核心要求：

* ✅ 状态清晰（State Visibility）
* ✅ 行为明确（Action Clarity）
* ✅ 变化可感知（Feedback Transparency）
* ✅ AI可理解（Explainable Chaos）

---

## 🧠 单回合结构（标准模板）

每一回合必须严格遵循以下顺序：

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

## 🧩 1. Header（视觉锚点）

```text
==============================
🃏 Chaos Blackjack
==============================
Turn: 3
```

---

## 🧩 2. Game State（核心信息）

```text
Your Hand:
  [7♠, 9♦]  → Total: 16

Dealer:
  [6♣, ?]
```

👉 规则：

* 必须对齐
* 必须显示总点数
* 必须区分可见/不可见信息

---

## 🧩 3. Chaos Effects（AI行为展示）

```text
------------------------------
🤖 Chaos AI Active:
"You look too comfortable..."

⚡ Active Effects:
- All 10 cards are worth 8 (this turn)
- Bust converts to half score
------------------------------
```

👉 规则：

* AI行为必须显式展示
* 效果必须列表化
* 必须说明持续时间（如this turn）

---

## 🧩 4. Items（玩家资源）

```text
🎒 Items:
  1. Peek (1 use)
  2. Shield (1 use)
```

👉 规则：

* 显示剩余次数
* 顺序编号

---

## 🧩 5. Actions（主操作）

```text
Available Actions:
  1. Hit
  2. Stand
  3. Use Item
```

👉 动态生成（受AI影响）

例如：

```text
⚡ Effect: Forced Hit

Available Actions:
  1. Hit
```

---

## 🧩 6. Commands（辅助指令）

```text
Commands:
  info   → 查看当前规则
  ai     → 查看AI解释
  items  → 查看道具详情
  debug  → (dev only)
  quit   → 退出游戏
```

---

## 🧩 7. Input（统一入口）

```text
> 
```

### 支持输入：

| 输入        | 含义       |
| --------- | -------- |
| 1 / hit   | Hit      |
| 2 / stand | Stand    |
| 3         | Use Item |
| info      | 查看规则     |
| ai        | AI解释     |
| quit      | 退出       |

---

## 🧩 8. 子菜单（Use Item）

```text
Choose Item:
  1. Peek
  2. Shield

> 
```

---

## 🔁 9. 反馈阶段（必须明确）

### 玩家行为反馈

```text
You draw: 10♥
```

### Chaos反馈

```text
⚡ Chaos Effect Triggered:
10 → 8
```

### 状态变化

```text
New Total: 24
```

### 结果

```text
💀 BUST!
```

---

## 🤖 AI解释系统（可选但强烈建议）

```text
> ai

🤖 Chaos AI:
"You rely too much on high-value cards."
```

---

## 📊 info命令（规则可视化）

```text
> info

Current Rules:
- Card Value: modified (10 → 8)
- Bust Rule: modified (half penalty)
```

---

## 🧪 debug模式（开发用）

```text
> debug state
> debug rules
```

---

## ⚠️ UX设计约束（必须遵守）

### ❌ 禁止：

* 自由文本输入（无约束）
* 隐藏AI行为
* 不显示规则变化
* 模糊反馈（如“something happened”）

---

### ✅ 必须：

* 所有变化必须可见
* 所有行为必须可解释
* 所有输入必须受控

---

## 🎯 关键体验目标

玩家每回合必须清楚：

1. 我现在是什么状态
2. 规则有没有变化
3. 我可以做什么
4. AI刚刚做了什么


