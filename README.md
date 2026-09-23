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

任选一把 key。不设地址时，有 `TYPESAFE_API_KEY` 就走官方，否则才用 `OPENROUTER_API_KEY` 走 OpenRouter。不看 key 前缀。两边都认 `jev-latest`。

```bash
export TYPESAFE_API_KEY=tsk_...          # https://console.typesafe.ai
# 或
export OPENROUTER_API_KEY=sk-or-v1-...   # https://openrouter.ai/settings/keys
```

| 变量 | 作用 | 默认 |
| --- | --- | --- |
| `TYPESAFE_API_KEY` | TypeSafe key。两把都在时优先用这个 | — |
| `OPENROUTER_API_KEY` | OpenRouter key。没有 TypeSafe key、且未传 `--api-key` 时使用 | — |
| `TYPESAFE_BASE_URL` | 显式 API 根地址。一旦设置就不再自动选择，本地 mock 也用它 | 按 key 自动 |
| `TYPESAFE_MODEL` | 模型 ID | `jev-latest` |

共享选项写在子命令**前面**：`--api-key`、`--model`、`--base-url`、`--timeout`、`--json`。

OpenRouter 页面上的 `typesafe/jev-1.13`、`~typesafe/jev-latest` 打到 TypeSafe 时会自动去掉前缀。`https://openrouter.ai` 和 `https://openrouter.ai/api` 都会归一到 `POST /api/v1/systemone`。

## 传入待评估内容

四个子命令的 `state` 都一样，三选一：

```bash
jev-cli noul "这段文字" -q "Is this urgent?"
jev-cli noul -f ticket.txt -q "Is this urgent?"
cat ticket.txt | jev-cli noul -q "Is this urgent?"
```

加 `--json-state` 时，上面三种来源都会被解析成 JSON 对象或数组，而不是纯文本。位置参数和 `--file` 同时给时，用文件。

问题和选项说明尽量用英文。Jev 以英文训练为主，中文能跑，准确率通常更低。

下面示例里的数字只说明输出形状，不是固定结果。

## 判断 `noul`

返回「是」的概率，0 到 1。CLI 把 `>= 0.5` 印成「是」，否则印成「否」。没有单独的 confidence：0.5 附近就是拿不准。

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

从你给的选项里选一个，并给出每个选项的概率和 confidence。

```bash
jev-cli choice "My card was charged twice." \
  -q "Which team should handle this?" \
  -o billing="Payments, refunds" \
  -o technical="Bugs, outages" \
  -o sales
```

```text
选择 (choice): billing  (confidence=0.7800)
概率分布:
  billing: 0.8000
  technical: 0.1000
  sales: 0.1000
```

`-o/--option` 可重复，格式是 `name` 或 `name=描述`，至少 1 个。选项里没有现成答案时，加一个 `other` 或 `none` 兜底，比硬塞进错误类别更安全。概率加总为 1。

confidence 看概率有多集中：单峰高，分散低。低 confidence 表示该转人工或追问，不要直接采信。

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
打分 (score): 1.3000  (confidence=0.5400)
等级概率:
  [0] Cosmetic: 0.2000
  [1] Broken, workaround exists: 0.6000
  [2] Blocking, no workaround: 0.2000
```

`-l/--level` 从低到高、可重复、至少 2 个、最多 10 个。等级描述写具体情境，不要只写「低 / 中 / 高」。

## 分类 `classify`

单标签分类。内部就是一次 `choice`，标签是选项。默认问题是英文，可用 `-q` 换掉。类别很多时，先粗分再细分，比一次塞几十个标签更稳。

```bash
jev-cli classify "TypeError: cannot read property of undefined" \
  -l javascript -l python -l go -l rust
```

```text
分类 (classify): javascript  (confidence=0.7800)
各类别概率:
  javascript: 80.0%
  python: 10.0%
  go: 10.0%
  rust: 10.0%
```

`-l/--label` 至少 2 个，格式同样是 `name` 或 `name=描述`。

## 给脚本用

人读的结果在 stdout，token 用量在 stderr，管道不会被用量行污染。失败时退出码是 1，错误写到 stderr，形如 `错误: ...`。

只要原始 JSON。`--json` 必须写在子命令前面：

```bash
jev-cli --json classify "TypeError: cannot read property of undefined" \
  -l javascript -l python \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["answers"]["class"]["choice"])'
```

每个子命令一次只问一个问题。要在同一次请求里并行问多个问题，直接调 `jev_cli.client.evaluate()`。429 和 529 会按指数退避重试；仍失败就稍后再跑。

## 开发

```bash
uv run jev-cli --help
python -m jev_cli --help
```

给 coding agent 用的命令说明在 [`SKILL.md`](SKILL.md)。

## Pull Request

指向 `main` 的非草稿 PR 会自动请 GPT 审核。结果写在 PR 评论里，不挡住合并。每次新推送会再审一次。草稿不审。

审核跑在 GitHub Actions 上，模型是 OpenRouter 上的 `openai/gpt-4.1`。密钥只放在仓库 Secret `OPENROUTER_API_KEY`，不进 git。workflow 使用默认分支上的脚本，只读取 diff，不执行 PR 里的代码，所以 fork 的 PR 也能审。

## 许可

[MIT](LICENSE)。Copyright (c) 2026 Jochen.He。

## 链接

- 文档：https://docs.typesafe.ai
- API：`POST https://api.typesafe.ai/v1/systemone`
- 模型页：https://openrouter.ai/~typesafe/jev-latest
- TypeSafe 控制台：https://console.typesafe.ai
- OpenRouter keys：https://openrouter.ai/settings/keys
