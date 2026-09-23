---
name: jev-cli
description: "调用 TypeSafe Jev（System One 模型）做结构化判断的命令行工具：判断(noul, yes/no 概率)、选择(choice, 选项+概率分布)、打分(score, 有序等级+置信度)三大原语，以及衍生的单标签分类(classify)。当需要让模型对一段文本/状态返回可被代码直接消费的确定性判断（是否、选哪个、打几分、归为哪类），而非生成自然语言时使用。触发词：jev、jev-cli、noul、判断、选择、打分、分类、System One、结构化判断。"
metadata:
  requires:
    bins: ["jev-cli", "python3"]
---

# jev-cli — 调用 Jev 做结构化判断

Jev 是 TypeSafe 的 "System One" 模型：**不生成文本**，对一段 `state` 做类型化判断，直接返回结构化结果（概率 / 选择 / 打分），无需解析 JSON 字符串。

- 文档：https://docs.typesafe.ai/api
- 端点按 key 自动选择：TypeSafe `POST https://api.typesafe.ai/v1/systemone`，OpenRouter `POST https://openrouter.ai/api/v1/systemone`。不需要手改 `--base-url`。

## 何时使用

需要模型给出**可被代码直接消费的确定性判断**时使用：

- **判断**：某条内容是否满足某个条件（是否紧急、是否退款、是否含 PII）
- **选择**：从固定选项中选一个（工单分给哪个团队、代码是什么语言）
- **打分**：沿有序等级打分（bug 严重程度、客户情绪、相关度）
- **分类**：把内容归入给定类别（标签分类、意图识别）

**反触发**：需要生成自然语言、开放式对话、总结、写作 → 用普通 LLM，不要用 Jev（它不产 prose）。

## 前置配置

任选一把 key。不设地址时看哪个环境变量有值：`TYPESAFE_API_KEY` 走官方，没有它才认 `OPENROUTER_API_KEY` 走 OpenRouter。不看 key 前缀。两边都认 `jev-latest`。

```bash
export TYPESAFE_API_KEY=tsk_...
# 或
export OPENROUTER_API_KEY=sk-or-v1-...
```

| 环境变量 | 作用 | 默认值 |
| --- | --- | --- |
| `TYPESAFE_API_KEY` | TypeSafe key。与 OpenRouter key 同时存在时优先 | — |
| `OPENROUTER_API_KEY` | OpenRouter key。没有 TypeSafe key 时使用 | — |
| `TYPESAFE_BASE_URL` | 显式 API 根地址；设置后不再自动选择 | 按 key 自动 |
| `TYPESAFE_MODEL` | 模型 ID | `jev-latest` |

## 命令参考

`state`（待评估内容）三种传入方式：位置参数、`--file/-f`、管道 stdin；`--json-state` 可传 JSON 对象/数组。所有子命令支持 `--json`（输出原始 JSON）。

### 判断 `noul`

返回 yes 概率 (0~1)，近 1 为「是」，近 0 为「否」。

```bash
jev-cli noul "Help! My payouts have been failing for 3 days." \
  -q "Does this convey urgency?" --yes "Time-sensitive" --no "Not urgent"
# 判断 (noul): 0.9200  →  是 (yes) (92.0%)
```

- `-q/--question`（必填）yes/no 问题；`--yes`/`--no` 可选，界定「是/否」含义。
- noul 无独立 confidence 字段——0.5 附近即「是/否」概率接近。

### 选择 `choice`

返回概率最高的选项、每个选项的概率、confidence。

```bash
jev-cli choice "My card was charged twice." -q "Which team should handle this?" \
  -o billing="Payments, refunds" -o technical="Bugs, outages" -o sales
```

- `-o/--option` 可重复，格式 `name` 或 `name=描述`（无描述时值为 null）。
- 可传最多 255 个选项；建议加 `other`/`none of the above` 兜底。

### 打分 `score`

返回概率加权分数（可落在等级之间）、等级概率、confidence。

```bash
jev-cli score "The export button crashes Safari." -q "How severe?" \
  -l "Cosmetic" -l "Broken, workaround exists" -l "Blocking, no workaround"
# 打分 (score): 1.3000  (confidence=0.5400)
```

- `-l/--level` 可重复、**从低到高**、至少 2 个、最多 10 个。
- score 是各等级编号按概率加权求和；等级描述要写「情境」而非「程度词」。

### 分类 `classify`（由 choice 衍生）

内部即一次 `choice` 调用，分类标签作为 criteria。

```bash
jev-cli classify "TypeError: cannot read property of undefined" \
  -l javascript -l python -l go -l rust
# 分类 (classify): javascript  (confidence=0.7800)
```

- `-l/--label` 可重复，格式 `name` 或 `name=描述`；至少 2 个。
- 默认问题为英文（Jev 以英文训练为主），可用 `-q` 覆盖。

## 输出与脚本化

- **人类可读**：结果在 stdout，token 用量在 stderr（不污染管道）。
- **`--json`**：输出完整原始 JSON 响应（含 `answers`、`usage`、`model`），供脚本消费：

```bash
jev-cli --json classify "..." -l a -l b | python3 -c 'import json,sys; print(json.load(sys.stdin)["answers"]["class"]["choice"])'
```

## 关键语义

- **confidence**（choice/score 才有）：由概率分布集中度算得，单峰=高，分散=低。低 confidence 意味着「该转人工/追问」而非直接采信。
- **概率求和为 1**：choice 的 `probabilities`、score 的 `probabilities` 均如此。
- **一次请求可问多个问题**（并行求值、几乎不加时延）：本 CLI 每个子命令发一个问题；批量场景用 `client.evaluate(questions={...})` 或多次调用。
- **CJK 输入**：Jev 支持但准确率较低，questions/instructions 尽量用英文。

## 排障

- `错误: ... Invalid API key` / `User not found` → key 无效。TypeSafe 查 `TYPESAFE_API_KEY`，OpenRouter 查 `OPENROUTER_API_KEY`。
- `错误: 缺少 API Key...` → 两把 key 都没设。两把都设时走官方。要在官方 key 也存在时改走 OpenRouter，用 `--base-url https://openrouter.ai/api`。
- `429/529` → client 已做指数退避重试；仍失败则稍后再试。
- 想联调/验证请求体：`--base-url http://127.0.0.1:<port>` 指向本地 mock 服务器。
