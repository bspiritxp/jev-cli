"""``jev-cli`` — a command-line client for TypeSafe's Jev model.

Subcommands map to Jev's three primitives plus one derived command:

- ``noul``      判断：yes/no 概率
- ``choice``    选择：从给定选项中选一个
- ``score``     打分：沿有序等级打分
- ``classify``  分类：由 ``choice`` 衍生的单标签分类

The shared ``state`` is the content to evaluate. It is accepted as a positional
argument, via ``--file``, or from stdin; use ``--json-state`` to pass it as a
JSON object/array instead of plain text.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List, Optional

import typer

from jev_cli import client

app = typer.Typer(
    name="jev-cli",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False,
    help="调用 Jev (TypeSafe System One) 模型做结构化判断。",
)


@app.callback()
def _callback(
    ctx: typer.Context,
    api_key: Optional[str] = typer.Option(
        None,
        "--api-key",
        envvar=client.API_KEY_ENV,
        help=(
            "API Key。"
            f"优先环境变量 {client.API_KEY_ENV}，否则 {client.OPENROUTER_API_KEY_ENV}。"
        ),
    ),
    model: str = typer.Option(
        client.DEFAULT_MODEL,
        "--model",
        envvar=client.MODEL_ENV,
        help="模型 ID。两边都认 jev-latest；OpenRouter 的 typesafe/ 前缀在打 TypeSafe 时会去掉。",
    ),
    base_url: Optional[str] = typer.Option(
        None,
        "--base-url",
        envvar=client.BASE_URL_ENV,
        help="API 根地址。省略时按 key 自动选择。显式设置始终优先，本地 mock 用这个。",
    ),
    timeout: float = typer.Option(60.0, "--timeout", help="请求超时（秒）。"),
    json_output: bool = typer.Option(
        False, "--json", is_flag=True, help="输出原始 JSON 响应。"
    ),
) -> None:
    """共享选项。"""
    ctx.obj = {
        "api_key": api_key,
        "model": model,
        "base_url": base_url,
        "timeout": timeout,
        "json_output": json_output,
    }


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _resolve_state(state: Optional[str], file: Any, json_state: bool) -> Any:
    """Return the state as a string or parsed JSON (object/array)."""
    if file is not None:
        raw = file.read()
    elif state is not None:
        raw = state
    elif not sys.stdin.isatty():
        raw = sys.stdin.read()
    else:
        raise typer.BadParameter(
            "缺少 state：请通过位置参数、--file 或标准输入提供待评估内容。"
        )

    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    raw = raw.strip()

    if json_state:
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise typer.BadParameter(f"state 不是合法 JSON：{exc}") from exc
    return raw


def _parse_name_value(items: List[str], option_name: str) -> Dict[str, Optional[str]]:
    """Parse ``--option name=desc`` (or bare ``name``) into a dict."""
    result: Dict[str, Optional[str]] = {}
    for item in items:
        if "=" in item:
            name, _, desc = item.partition("=")
            name, desc = name.strip(), desc.strip()
        else:
            name, desc = item.strip(), None
        if not name:
            raise typer.BadParameter(f"{option_name} 的选项名不能为空。")
        if name in result:
            raise typer.BadParameter(f"选项 '{name}' 重复。")
        result[name] = desc or None
    return result


def _run(
    ctx: typer.Context,
    state: Any,
    questions: Dict[str, Any],
    question_id: str,
) -> Dict[str, Any]:
    """Call the API and return the single answer for ``question_id``."""
    opts = ctx.obj
    response = client.evaluate(
        state=state,
        questions=questions,
        api_key=opts["api_key"],
        model=opts["model"],
        base_url=opts["base_url"],
        timeout=opts["timeout"],
    )
    if opts["json_output"]:
        typer.echo(json.dumps(response, ensure_ascii=False, indent=2))
        raise typer.Exit()

    answer = response.get("answers", {}).get(question_id)
    if answer is None:
        raise client.APIError(f"响应中缺少答案 '{question_id}'：{response}")

    usage = response.get("usage")
    if usage:
        typer.echo(
            f"usage: input={usage.get('input_tokens')} tokens, "
            f"output={usage.get('output_tokens')} tokens",
            err=True,
        )
    return answer


# --------------------------------------------------------------------------- #
# 判断 / noul
# --------------------------------------------------------------------------- #


@app.command("noul", help="判断：对一条 yes/no 问题返回『是』的概率 (0~1)。")
def noul(
    ctx: typer.Context,
    state: Optional[str] = typer.Argument(None, help="待评估的内容。"),
    question: str = typer.Option(..., "--question", "-q", help="要评估的 yes/no 问题。"),
    yes: Optional[str] = typer.Option(None, "--yes", help="『是』（值接近 1）意味着什么。"),
    no: Optional[str] = typer.Option(None, "--no", help="『否』（值接近 0）意味着什么。"),
    file: Optional[typer.FileText] = typer.Option(
        None, "--file", "-f", help="从文件读取 state。"
    ),
    json_state: bool = typer.Option(
        False, "--json-state", help="将 state 解析为 JSON 对象/数组。"
    ),
) -> None:
    """判断（Noul）：yes/no 概率。"""
    value = _resolve_state(state, file, json_state)
    answer = _run(
        ctx,
        value,
        {"noul": client.noul_question(question, yes=yes, no=no)},
        "noul",
    )
    probability = float(answer["noul"])
    verdict = "是 (yes)" if probability >= 0.5 else "否 (no)"
    typer.echo(
        f"判断 (noul): {probability:.4f}  →  {verdict} ({probability * 100:.1f}%)"
    )


# --------------------------------------------------------------------------- #
# 选择 / choice
# --------------------------------------------------------------------------- #


@app.command("choice", help="选择：从给定选项中选一个，并给出每个选项的概率。")
def choice(
    ctx: typer.Context,
    state: Optional[str] = typer.Argument(None, help="待评估的内容。"),
    question: str = typer.Option(..., "--question", "-q", help="要做的选择问题。"),
    option: List[str] = typer.Option(
        ...,
        "--option",
        "-o",
        help="选项，格式 name 或 name=描述（可重复）。",
    ),
    file: Optional[typer.FileText] = typer.Option(
        None, "--file", "-f", help="从文件读取 state。"
    ),
    json_state: bool = typer.Option(
        False, "--json-state", help="将 state 解析为 JSON 对象/数组。"
    ),
) -> None:
    """选择（Choice）：从一组选项中选一个。"""
    criteria = _parse_name_value(option, "--option")
    if not criteria:
        raise typer.BadParameter("至少需要一个 --option。")
    value = _resolve_state(state, file, json_state)
    answer = _run(
        ctx,
        value,
        {"choice": client.choice_question(question, criteria)},
        "choice",
    )
    typer.echo(
        f"选择 (choice): {answer['choice']}  (confidence={answer['confidence']:.4f})"
    )
    typer.echo("概率分布:")
    for name, prob in answer["probabilities"].items():
        typer.echo(f"  {name}: {prob:.4f}")


# --------------------------------------------------------------------------- #
# 打分 / score
# --------------------------------------------------------------------------- #


@app.command("score", help="打分：沿有序等级打分，可落在两个等级之间。")
def score(
    ctx: typer.Context,
    state: Optional[str] = typer.Argument(None, help="待评估的内容。"),
    question: str = typer.Option(..., "--question", "-q", help="要打分的问题。"),
    level: List[str] = typer.Option(
        ...,
        "--level",
        "-l",
        help="等级描述（从低到高，可重复，至少 2 个）。",
    ),
    file: Optional[typer.FileText] = typer.Option(
        None, "--file", "-f", help="从文件读取 state。"
    ),
    json_state: bool = typer.Option(
        False, "--json-state", help="将 state 解析为 JSON 对象/数组。"
    ),
) -> None:
    """打分（Score）：沿有序等级打分。"""
    levels = [lvl.strip() for lvl in level]
    if len(levels) < 2:
        raise typer.BadParameter("至少需要 2 个 --level。")
    value = _resolve_state(state, file, json_state)
    answer = _run(
        ctx,
        value,
        {"score": client.score_question(question, levels)},
        "score",
    )
    typer.echo(
        f"打分 (score): {answer['score']:.4f}  (confidence={answer['confidence']:.4f})"
    )
    typer.echo("等级概率:")
    legend = answer.get("legend", {})
    for level_key, prob in answer["probabilities"].items():
        desc = legend.get(level_key, level_key)
        typer.echo(f"  [{level_key}] {desc}: {prob:.4f}")


# --------------------------------------------------------------------------- #
# 分类 / classify (derived from choice)
# --------------------------------------------------------------------------- #


@app.command("classify", help="分类：单标签分类（由 choice 衍生）。")
def classify(
    ctx: typer.Context,
    state: Optional[str] = typer.Argument(None, help="待评估的内容。"),
    label: List[str] = typer.Option(
        ...,
        "--label",
        "-l",
        help="类别标签，格式 name 或 name=描述（可重复）。",
    ),
    question: str = typer.Option(
        "Which of the following categories does this content belong to?",
        "--question",
        "-q",
        help="分类问题（默认英文，因 Jev 以英文训练为主）。",
    ),
    file: Optional[typer.FileText] = typer.Option(
        None, "--file", "-f", help="从文件读取 state。"
    ),
    json_state: bool = typer.Option(
        False, "--json-state", help="将 state 解析为 JSON 对象/数组。"
    ),
) -> None:
    """分类（classify）：由 Choice 衍生的单标签分类。

    内部即一个 ``choice`` 问题，``criteria`` 为各分类标签；返回概率最高的
    类别及完整概率分布。对于深层/大规模分类体系，可级联多次调用。
    """
    criteria = _parse_name_value(label, "--label")
    if len(criteria) < 2:
        raise typer.BadParameter("分类至少需要 2 个 --label。")
    value = _resolve_state(state, file, json_state)
    answer = _run(
        ctx,
        value,
        {"class": client.choice_question(question, criteria)},
        "class",
    )
    typer.echo(
        f"分类 (classify): {answer['choice']}  (confidence={answer['confidence']:.4f})"
    )
    typer.echo("各类别概率:")
    ranked = sorted(answer["probabilities"].items(), key=lambda kv: -kv[1])
    for name, prob in ranked:
        typer.echo(f"  {name}: {prob * 100:.1f}%")


def main() -> None:
    """CLI 入口。"""
    try:
        app()
    except client.TypeSafeError as exc:
        typer.echo(f"错误: {exc}", err=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
