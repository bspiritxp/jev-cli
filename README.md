# jev-cli

把一段内容交给 [Jev](https://docs.typesafe.ai)，拿回可以直接写进脚本的判断，而不是一段还要再解析的文字。

Jev 是 TypeSafe 的 System One 模型。它不写文章、不聊天。你给它一段 `state` 和一个有类型的问题，它返回概率、选项或分数。这个仓库把这件事做成命令行：人可以试，管道和 CI 也可以直接调用。

普通聊天模型适合生成文字。Jev 适合「是不是、选哪个、打几分、归哪类」。结果是数和标签：stdout 给结果，stderr 给 token 用量，加 `--json` 就给原始响应。

## 适合做什么

| 你想知道 | 命令 | 例如 |
| --- | --- | --- |
| 这条内容是否满足某个条件 | `noul` | 是否紧急、是否该退款、是否含个人信息 |
| 该从固定选项里选哪一个 | `choice` | 工单分给哪个团队、走哪条处理路径 |
| 沿一组有序等级打几分 | `score` | bug 严重程度、客户情绪、相关度 |
| 归入哪个标签 | `classify` | 语言、意图、类别 |

不适合写文案、总结、开放式问答、多轮对话。那种需求用普通 LLM。Jev 不产散文。

## 安装

需要 Python 3.14+ 和 [uv](https://docs.astral.sh/uv/)。

装成命令：

```bash
uv tool install git+https://github.com/bspiritxp/jev-cli
jev-cli --help
```

或克隆后在仓库里跑：

```bash
git clone https://github.com/bspiritxp/jev-cli
cd jev-cli
uv sync
uv run jev-cli --help
```

## 配置

优先级：自定义端点 > 官方 key > OpenRouter key。不看 key 前缀。

自定义端点写在 `$HOME/.config/jev-cli/setting.yaml`。配齐 `base_url` 和 `api_key` 后，后续命令默认走它，不再看环境变量里的 key。

```bash
jev-cli setup
# 或非交互
jev-cli setup \
  --base-url https://example.com \
  --api-key sk-... \
  --model jev-latest
jev-cli setup --show
jev-cli setup --clear
```

文件形如：

```yaml
base_url: "https://example.com"
api_key: "sk-..."
model_name: "jev-latest"
```

没配自定义端点时，有 `TYPESAFE_API_KEY` 就走官方，否则才用 `OPENROUTER_API_KEY` 走 OpenRouter。两边都认 `jev-latest`。

```bash
export TYPESAFE_API_KEY=tsk_...          # https://console.typesafe.ai
# 或
export OPENROUTER_API_KEY=sk-or-v1-...   # https://openrouter.ai/settings/keys
```

| 来源 | 作用 | 何时生效 |
| --- | --- | --- |
| `setting.yaml` 的 `base_url` / `api_key` / `model_name` | 自定义端点 | 配齐 `base_url` 与 `api_key` 后优先于环境变量 |
| `--api-key` / `--base-url` / `--model` | 单次覆盖对应字段 | 始终最高。本地 mock 用 `--base-url` |
| `TYPESAFE_API_KEY` | TypeSafe key，走官方 | 没有自定义端点时，优先于 OpenRouter |
| `OPENROUTER_API_KEY` | OpenRouter key | 没有自定义端点，且没有官方 key 时 |
| `TYPESAFE_BASE_URL` | 显式 API 根地址 | 没有自定义 `base_url`，也没传 `--base-url` 时 |
| `TYPESAFE_MODEL` | 模型 ID，默认 `jev-latest` | 没有自定义 `model_name`，也没传 `--model` 时 |

共享选项写在子命令**前面**：`--api-key`、`--model`、`--base-url`、`--timeout`、`--json`。`setup` 自己的 `--base-url`、`--api-key`、`--model` 写在 `setup` **后面**，只用于保存，不发起请求。

已保存自定义端点时，只改 `--api-key` 不会换 host。要临时改走官方，同时传 `--api-key` 和 `--base-url https://api.typesafe.ai`，或先 `jev-cli setup --clear`。

OpenRouter 页面上的 `typesafe/jev-1.13`、`~typesafe/jev-latest` 只有打到 `api.typesafe.ai` 时才会去掉前缀。自定义端点和 OpenRouter 原样发送 `model_name`。`https://openrouter.ai` 和 `https://openrouter.ai/api` 都会归一到 `POST /api/v1/systemone`。

## 传入待评估内容

`noul`、`choice`、`score` 的 `state` 三选一，一次一份：

```bash
jev-cli noul "这段文字" -q "Is this urgent?"
jev-cli noul -f ticket.txt -q "Is this urgent?"
cat ticket.txt | jev-cli noul -q "Is this urgent?"
```

`classify` 的位置参数可以重复。每一项单独请求，按输入顺序输出。`--file` 和管道仍然是一项。单个位置参数和 `--file` 同时给时，用文件；多个位置参数不能再加 `--file`。

加 `--json-state` 时，上面这些来源都会被解析成 JSON 对象或数组，而不是纯文本。`classify` 的每个位置参数各自解析。

问题和选项说明尽量用英文。Jev 以英文训练为主，中文能跑，准确率通常更低。

下面示例里的数字只说明输出形状，不是固定结果。

## 判断 `noul`

返回「是」的概率，0 到 1。CLI 把 `>= 0.5` 印成「是」，否则印成「否」。没有单独的置信度：0.5 附近就是拿不准。

```bash
jev-cli noul "Help! My payouts have been failing for 3 days." \
  -q "Does this convey urgency?" \
  --yes "Time-sensitive" \
  --no "Not urgent"
```

```text
判断 (noul): 0.9200  →  是 (yes) (92.0%)
```

`-q/--question` 必填。`--yes` / `--no` 可选，用来界定接近 1 和接近 0 分别是什么意思。

## 选择 `choice`

从你给的选项里选一个，并给出每个选项的概率和置信度。

```bash
jev-cli choice "My card was charged twice." \
  -q "Which team should handle this?" \
  -o billing="Payments, refunds" \
  -o technical="Bugs, outages" \
  -o sales
```

```text
选择 (choice): billing  (置信度=0.7800)
概率分布:
  billing: 0.8000
  technical: 0.1000
  sales: 0.1000
```

`-o/--option` 可重复，格式是 `name` 或 `name=描述`，至少 1 个。选项里没有现成答案时，加一个 `other` 或 `none` 兜底，比硬塞进错误类别更安全。概率加总为 1。

置信度看概率有多集中：单峰高，分散低。低置信度表示该转人工或追问，不要直接采信。

## 打分 `score`

沿一组有序等级打分。分数是等级编号的概率加权和，可以落在两个等级之间。

```bash
jev-cli score "The export button crashes Safari." \
  -q "How severe?" \
  -l "Cosmetic" \
  -l "Broken, workaround exists" \
  -l "Blocking, no workaround"
```

```text
打分 (score): 1.3000  (置信度=0.5400)
等级概率:
  [0] Cosmetic: 0.2000
  [1] Broken, workaround exists: 0.6000
  [2] Blocking, no workaround: 0.2000
```

`-l/--level` 从低到高、可重复、至少 2 个、最多 10 个。等级描述写具体情境，不要只写「低 / 中 / 高」。

## 分类 `classify`

单标签分类。内部就是一次 `choice`，标签是选项。可以传多个位置参数，每项单独请求，结果按输入顺序打印。默认问题是英文，可用 `-q` 换掉。类别很多时，先粗分再细分，比一次塞几十个标签更稳。

```bash
jev-cli classify "TypeError: cannot read property of undefined" \
  -l javascript -l python -l go -l rust

jev-cli classify 鼠标 键盘 手柄 \
  -q "Is this a gaming peripheral or an office peripheral?" \
  -l "游戏外设=Used mainly for playing video games" \
  -l "办公外设=Used mainly for office or productivity work"
```

单项输出：

```text
分类 (classify): javascript  (置信度=0.7800)
各类别概率:
  javascript: 80.0%
  python: 10.0%
  go: 10.0%
  rust: 10.0%
```

多项时不逐项展开，打成一张表。概率是该项胜出类别的概率：

```text
项      分类      概率     置信度
鼠标    办公外设  96.0%    0.9300
键盘    办公外设  97.0%    0.9400
手柄    游戏外设  100.0%   0.9900
```

`-l/--label` 至少 2 个，格式同样是 `name` 或 `name=描述`。

## 给脚本用

人读的结果在 stdout，token 用量在 stderr，管道不会被用量行污染。失败时退出码是 1，错误写到 stderr，形如 `错误: ...`。

只要原始 JSON。`--json` 必须写在子命令前面。只有一项时仍是原始响应：

```bash
jev-cli --json classify "TypeError: cannot read property of undefined" \
  -l javascript -l python \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["answers"]["class"]["choice"])'
```

`classify` 传入多项时，`--json` 改为数组。先把整段读进变量，不要对 stdin 调两次 `json.load`：

```bash
jev-cli --json classify 鼠标 键盘 -l "游戏外设" -l "办公外设" \
  | python3 -c 'import json,sys; rows=json.load(sys.stdin); [print(row["item"], row["response"]["answers"]["class"]["choice"]) for row in rows]'
```

每个请求只问一个问题。`classify` 的多项是多次请求，不是一次请求里的多个问题。要在同一次请求里对同一份 `state` 并行问多个问题，直接调 `jev_cli.client.evaluate()`。429 和 529 会按指数退避重试；仍失败就稍后再跑。

## 开发

```bash
uv run jev-cli --help
python -m jev_cli --help
```

给 coding agent 用的命令说明在 [`SKILL.md`](SKILL.md)。

## 许可

[MIT](LICENSE)。Copyright (c) 2026 Jochen.He。

## 链接

- 文档：https://docs.typesafe.ai
- API：`POST https://api.typesafe.ai/v1/systemone`
- 模型页：https://openrouter.ai/~typesafe/jev-latest
- TypeSafe 控制台：https://console.typesafe.ai
- OpenRouter keys：https://openrouter.ai/settings/keys
