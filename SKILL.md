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
- 端点优先级：`~/.config/jev-cli/setting.yaml` 自定义端点 > TypeSafe `POST https://api.typesafe.ai/v1/systemone` > OpenRouter `POST https://openrouter.ai/api/v1/systemone`。

## 何时使用

需要模型给出**可被代码直接消费的确定性判断**时使用：

- **判断**：某条内容是否满足某个条件（是否紧急、是否退款、是否含 PII）
- **选择**：从固定选项中选一个（工单分给哪个团队、代码是什么语言）
- **打分**：沿有序等级打分（bug 严重程度、客户情绪、相关度）
- **分类**：把内容归入给定类别（标签分类、意图识别）

**反触发**：需要生成自然语言、开放式对话、总结、写作 → 用普通 LLM，不要用 Jev（它不产 prose）。

## 前置配置

优先级：自定义端点 > `TYPESAFE_API_KEY` > `OPENROUTER_API_KEY`。不看 key 前缀。两边都认 `jev-latest`。

```bash
jev-cli setup --base-url https://example.com --api-key sk-... --model jev-latest
# 或交互：jev-cli setup
# 查看 / 删除：jev-cli setup --show | jev-cli setup --clear
```

配齐后写入 `$HOME/.config/jev-cli/setting.yaml`（`base_url`、`api_key`、`model_name`），之后默认走自定义端点。没有该文件时：

```bash
export TYPESAFE_API_KEY=tsk_...
# 或
export OPENROUTER_API_KEY=sk-or-v1-...
```

| 来源 | 作用 | 默认值 |
| --- | --- | --- |
| `setting.yaml` | 自定义端点。配齐 `base_url` 与 `api_key` 后优先于环境变量 | — |
| `TYPESAFE_API_KEY` | TypeSafe key。没有自定义端点时优先 | — |
| `OPENROUTER_API_KEY` | OpenRouter key。没有自定义端点、也没有 TypeSafe key 时使用 | — |
| `TYPESAFE_BASE_URL` | 显式 API 根地址；自定义 `base_url` 或 `--base-url` 存在时不生效 | 按 key 自动 |
| `TYPESAFE_MODEL` | 模型 ID。自定义 `model_name` 或 `--model` 存在时不生效 | `jev-latest` |

单次覆盖写在子命令前：`--api-key`、`--base-url`、`--model`。已保存自定义端点时，只改 key 不会换 host。

## 命令参考

`noul` / `choice` / `score` 的 `state` 三选一：位置参数、`--file/-f`、管道 stdin。`classify` 的位置参数可重复，每项单独请求；`--file` 和管道仍是一项。`--json-state` 把每一项解析为 JSON 对象/数组。`--json` 在一项时是原始响应；`classify` 多项时是 `[{"item","response"}, ...]`。

### 判断 `noul`

返回 yes 概率 (0~1)，近 1 为「是」，近 0 为「否」。

```bash
jev-cli noul "Help! My payouts have been failing for 3 days." \
  -q "Does this convey urgency?" --yes "Time-sensitive" --no "Not urgent"
# 判断 (noul): 0.9200  →  是 (yes) (92.0%)
```

- `-q/--question`（必填）yes/no 问题；`--yes`/`--no` 可选，界定「是/否」含义。
- noul 无独立置信度——0.5 附近即「是/否」概率接近。

### 选择 `choice`

返回概率最高的选项、每个选项的概率、置信度。

```bash
jev-cli choice "My card was charged twice." -q "Which team should handle this?" \
  -o billing="Payments, refunds" -o technical="Bugs, outages" -o sales
```

- `-o/--option` 可重复，格式 `name` 或 `name=描述`（无描述时值为 null）。
- 可传最多 255 个选项；建议加 `other`/`none of the above` 兜底。

### 打分 `score`

返回概率加权分数（可落在等级之间）、等级概率、置信度。

```bash
jev-cli score "The export button crashes Safari." -q "How severe?" \
  -l "Cosmetic" -l "Broken, workaround exists" -l "Blocking, no workaround"
# 打分 (score): 1.3000  (置信度=0.5400)
```

- `-l/--level` 可重复、**从低到高**、至少 2 个、最多 10 个。
- score 是各等级编号按概率加权求和；等级描述要写「情境」而非「程度词」。

### 分类 `classify`（由 choice 衍生）

内部即一次 `choice` 调用，分类标签作为 criteria。多个位置参数会逐项请求，不要把多项拼进同一份 `state`。

```bash
jev-cli classify "TypeError: cannot read property of undefined" \
  -l javascript -l python -l go -l rust
# 分类 (classify): javascript  (置信度=0.7800)

jev-cli classify 鼠标 键盘 手柄 -l "游戏外设" -l "办公外设"
```

- `-l/--label` 可重复，格式 `name` 或 `name=描述`；至少 2 个。
- 反直觉的边界规则（本地法规、行业约定）显式写进对应 label 的描述即可显著提升准确率：实测某分类任务 83% → 100%。同样适用于 `choice` 的 `-o`。
- 位置参数可重复。每项一次请求。多项的人类可读输出是一张表（项、分类、概率、置信度），不是逐项展开。单项输出形状不变。
- `--json`：一项时仍是原始响应；多项时是 `[{"item","response"}, ...]`。
- 默认问题为英文，可用 `-q` 覆盖；中文问题实测与英文等价。

## 输出与脚本化

- **人类可读**：结果在 stdout，token 用量在 stderr（不污染管道）。
- **`--json`**：一项时是完整原始 JSON（含 `answers`、`usage`、`model`）。`classify` 多项时是 `[{"item","response"}, ...]`，先 `json.load` 一次再遍历：

```bash
jev-cli --json classify "..." -l a -l b | python3 -c 'import json,sys; print(json.load(sys.stdin)["answers"]["class"]["choice"])'
jev-cli --json classify 鼠标 键盘 -l a -l b | python3 -c 'import json,sys; rows=json.load(sys.stdin); print(rows[0]["item"], rows[0]["response"]["answers"]["class"]["choice"])'
```

## 关键语义

- **置信度**（choice/score 才有，JSON 字段仍是 `confidence`）：由概率分布集中度算得，单峰=高，分散=低。低置信度意味着「该转人工/追问」而非直接采信。
- **置信度会高估**：在反直觉的边界规则上可能高置信度答错（实测 0.91/0.94），不能当安全网；只在明显偏低（如 < 0.6）时当作转人工信号。
- **概率求和为 1**：choice 的 `probabilities`、score 的 `probabilities` 均如此。
- **一次请求可问多个问题**（并行求值、几乎不加时延）：本 CLI 每个请求发一个问题。`classify` 多项是包装层循环，每项一次请求。要对同一份 `state` 并行问多个问题，用 `client.evaluate(questions={...})`。
- **CJK 输入**：中文可用。实测中文标签、中文问题与英文等价（分类任务 100% vs 100%）。准确率瓶颈通常在**领域/本地规则知识**，而非语言——把易错的边界规则显式写进 label 描述即可修复（实测 83% → 100%）。

## 排障

- `错误: ... Invalid API key` / `User not found` → key 无效。自定义端点查 `setting.yaml`，否则 TypeSafe 查 `TYPESAFE_API_KEY`，OpenRouter 查 `OPENROUTER_API_KEY`。
- `错误: 缺少 API Key...` → 没配自定义端点，两把环境变量 key 也都没设。已配置自定义端点时环境变量不会自动顶上；要改回官方，`jev-cli setup --clear`，或同时传 `--api-key` 与 `--base-url https://api.typesafe.ai`。
- `429/529` → client 已做指数退避重试；仍失败则稍后再试。
- 想联调/验证请求体：`--base-url http://127.0.0.1:<port>` 指向本地 mock 服务器。
