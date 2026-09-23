# AGENT.md

本文件为在此仓库工作的 AI 编码代理提供上下文与约定。

## 项目概述

`jev-cli` 是一个用 [Typer](https://typer.tiangolo.com/) 实现的命令行工具，调用 TypeSafe 的 **Jev**（首个 "System One" 模型）做结构化判断。Jev 不生成文本，而是对一段 `state`（内容）做类型化判断，直接返回结构化结果（概率 / 选择 / 打分），无需解析 JSON 字符串。

- 上游文档：https://docs.typesafe.ai/api
- TypeSafe：`POST https://api.typesafe.ai/v1/systemone`
- OpenRouter：`POST https://openrouter.ai/api/v1/systemone`（与 TypeSafe SDK 同形；裸模型名 `jev-latest` / `jev-1.13` 由 OpenRouter 映射到 `typesafe/`）
- 模型页：https://openrouter.ai/typesafe/jev-1.13 、 https://openrouter.ai/~typesafe/jev-latest

## 技术栈与工具链

- Python **3.14**（见 `.python-version`）
- 依赖管理：**uv**（`pyproject.toml` + `uv.lock`，build backend 为 `uv_build`）
- 仅一个运行时依赖：`typer>=0.27.2`；HTTP 调用用标准库 `urllib`（不引入 requests/httpx）
- 入口点：`jev-cli = "jev_cli:main"`（`src/jev_cli/__init__.py` 导出 `main`）

## 目录结构

```
src/jev_cli/
├── __init__.py   # 导出 app / main 及 client 的公共 API
├── __main__.py   # 支持 python -m jev_cli
├── client.py     # HTTP 客户端 + 问题构造器 + 异常/重试
└── cli.py        # Typer 应用与四个子命令
```

## 开发循环

```bash
uv sync                 # 安装依赖（.venv）
uv run jev-cli --help   # 或 .venv/bin/jev-cli --help
python -m jev_cli noul --help
.venv/bin/python -m py_compile src/jev_cli/*.py   # 快速语法检查
```

## 对外 API 契约（client.py）

请求体顶层为 `{"state", "model", "questions"}`；`questions` 是「问题 id → 问题对象」的映射，响应在 `answers` 下按相同 id 返回。

三种原语（问题对象）：

| 原语 | `type` | `criteria` | 答案字段 |
| --- | --- | --- | --- |
| Noul（判断） | `"noul"` | 可选 `{true, false}` 描述 | `noul`：0~1 的 yes 概率 |
| Choice（选择） | `"choice"` | 必填 `map<选项, 描述|null>` | `choice`、`probabilities`、`confidence` |
| Score（打分） | `"score"` | 必填有序数组（2~10 个等级描述） | `score`、`legend`、`probabilities`、`confidence` |

错误码：401（鉴权）、400/422（校验，OpenRouter 用 400）、402（额度，`APIError`）、429/529（指数退避重试，client 已实现）、其余转 `APIError`。路由：`resolve_endpoint` 只看环境变量，不看 key 前缀。显式 `base_url` 或 `TYPESAFE_BASE_URL` 优先；否则 `TYPESAFE_API_KEY` 走官方，没有它才认 `OPENROUTER_API_KEY`。

## CLI 约定（cli.py）

- 四个子命令：`noul` / `choice` / `score` / `classify`（分类由 Choice 衍生，内部构造一个 choice 问题）。
- 共享选项在 `@app.callback()` 中定义并存进 `ctx.obj`：`--api-key`（envvar `TYPESAFE_API_KEY`，缺省再读 `OPENROUTER_API_KEY`）、`--model`（默认 `jev-latest`）、`--base-url`（省略时按环境变量选择：有 `TYPESAFE_API_KEY` 走官方，否则有 `OPENROUTER_API_KEY` 走 OpenRouter；显式地址始终优先）、`--timeout`、`--json`。
- `state` 通过三种方式之一传入：位置参数、`--file/-f`、管道 stdin；`--json-state` 把 state 解析为 JSON 对象/数组。
- `--json` 输出原始 JSON 响应；人类可读模式下 token 用量打印到 **stderr**，结果打印到 stdout。
- 异常处理：`client.TypeSafeError` 在 `main()` 中被捕获并打印 `错误: ...` 到 stderr 后以 exit code 1 退出；`typer.BadParameter` 由 Typer 自身渲染。

## 修改指南

- 新增子命令时复用 `client.py` 的问题构造器（`noul_question` / `choice_question` / `score_question`）与 `_run()` / `_resolve_state()`。
- 改变请求/响应结构前，先对照 `docs.typesafe.ai/api` 契约，并同步更新 `client.py` 的 docstring 与 `README.md`。
- 依赖保持最小：HTTP 用 `urllib`；除非有硬需求，不要引入 requests/httpx/rich。

## 测试方法

无正式测试套件。联调用一个本地 mock HTTPServer 指到 `--base-url http://127.0.0.1:<port>` 验证请求体与输出格式；`--json` 用于脚本化断言。改动后至少跑一遍四子命令的 `--help`、`py_compile` 与一次 mock 冒烟。
