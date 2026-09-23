# jev-cli

一个用 [Typer](https://typer.tiangolo.com/) 实现的命令行工具，调用 TypeSafe 的 **Jev**（首个 "System One" 模型）做结构化判断。

Jev 不生成文本，而是对一段 `state`（内容）做类型化的判断，直接返回结构化结果（概率 / 选择 / 打分），无需解析 JSON 字符串。

- 文档：https://docs.typesafe.ai
- 模型页（OpenRouter）：https://openrouter.ai/~typesafe/jev-latest
- API 端点：`POST https://api.typesafe.ai/v1/systemone`

## 安装

```bash
uv sync
```

## 配置

任选一把 key。不设地址时看哪个环境变量有值：`TYPESAFE_API_KEY` 走官方，没有它才认 `OPENROUTER_API_KEY` 走 OpenRouter。不看 key 前缀。两边都认 `jev-latest`。

```bash
export TYPESAFE_API_KEY=tsk_...          # TypeSafe 控制台 https://console.typesafe.ai
# 或
export OPENROUTER_API_KEY=sk-or-v1-...   # https://openrouter.ai/settings/keys
```

| 变量 | 作用 | 默认值 |
| --- | --- | --- |
| `TYPESAFE_API_KEY` | TypeSafe key。与 OpenRouter key 同时存在时优先用这个 | — |
| `OPENROUTER_API_KEY` | OpenRouter key。仅当没有 TypeSafe key、且未传 `--api-key` 时使用 | — |
| `TYPESAFE_BASE_URL` | 显式 API 根地址。一旦设置就不再自动选择（本地 mock 也用它） | 按 key 自动 |
| `TYPESAFE_MODEL` | 模型 ID | `jev-latest` |

`https://openrouter.ai` 和 `https://openrouter.ai/api` 都会被归一到 `POST /api/v1/systemone`。OpenRouter 模型页上的 `typesafe/jev-1.13`、`~typesafe/jev-latest` 打到 TypeSafe 时会去掉前缀。

## 子命令

三个基本子命令对应 Jev 的三大原语，另有一个衍生子命令：

| 命令 | 功能 | 原语 |
| --- | --- | --- |
| `noul` | 判断：yes/no 概率 (0~1) | Noul |
| `choice` | 选择：从选项中选一个 + 概率分布 | Choice |
| `score` | 打分：沿有序等级打分 + 等级概率 | Score |
| `classify` | 分类：单标签分类（由 Choice 衍生） | Choice |

`state`（待评估内容）可通过三种方式传入：位置参数、`--file/-f` 读文件、或管道标准输入；加 `--json-state` 可将其解析为 JSON 对象/数组。

### 判断 `noul`

```bash
jev-cli noul "Help! My payouts have been failing for 3 days." \
  -q "Does this convey urgency?" --yes "Time-sensitive" --no "Not urgent"
# 判断 (noul): 0.9200  →  是 (yes) (92.0%)
```

### 选择 `choice`

```bash
jev-cli choice "My card was charged twice." -q "Which team should handle this?" \
  -o billing="Payments, refunds" -o technical="Bugs, outages" -o sales
# 选择 (choice): billing  (confidence=0.7800)
# 概率分布:
#   billing: 0.8000
#   technical: 0.1000
#   sales: 0.1000
```

### 打分 `score`

```bash
jev-cli score "The export button crashes Safari." -q "How severe?" \
  -l "Cosmetic" -l "Broken, workaround exists" -l "Blocking, no workaround"
# 打分 (score): 1.3000  (confidence=0.5400)
# 等级概率:
#   [0] Cosmetic: 0.2000
#   [1] Broken, workaround exists: 0.6000
#   [2] Blocking, no workaround: 0.2000
```

### 分类 `classify`（衍生）

`classify` 内部就是一次 `choice` 调用，把各分类标签作为 `criteria`：

```bash
jev-cli classify "TypeError: cannot read property of undefined" \
  -l javascript -l python -l go -l rust
# 分类 (classify): javascript  (confidence=0.7800)
# 各类别概率:
#   javascript: 80.0%
#   python: 10.0%
#   go: 10.0%
#   rust: 10.0%
```

### 通用选项

- `--json`：输出原始 JSON 响应（便于脚本消费）
- `--model`：切换模型（如 `--model jev-1.13`）。两边都认 `jev-latest`
- `--base-url`：强制 API 根地址。省略则按 key 自动选择
- `--api-key`：覆盖环境变量。两把 key 都在时，用这个把 OpenRouter key 显式传进去

## 开发

```bash
uv run jev-cli --help
python -m jev_cli --help
```
