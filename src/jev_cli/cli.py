"""``jev-cli`` — a command-line client for TypeSafe's Jev model.

Subcommands map to Jev's three primitives, one derived command, and setup:

- ``noul``      判断：yes/no 概率
- ``choice``    选择：从给定选项中选一个
- ``score``     打分：沿有序等级打分
- ``classify``  分类：由 ``choice`` 衍生的单标签分类。位置参数可重复，每项单独请求
- ``setup``     配置自定义端点，写入 ``~/.config/jev-cli/setting.yaml``

The shared ``state`` is the content to evaluate. It is accepted as a positional
argument, via ``--file``, or from stdin; use ``--json-state`` to pass it as a
JSON object/array instead of plain text. ``classify`` accepts repeated
positionals and evaluates each one separately.
"""

from __future__ import annotations

import json
import sys
import unicodedata
from typing import Any, Dict, List, Optional

import typer

from jev_cli import client, settings

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
        help=(
            "API Key。优先级：该选项 > ~/.config/jev-cli/setting.yaml > "
            f"{client.API_KEY_ENV} > {client.OPENROUTER_API_KEY_ENV}。"
        ),
    ),
    model: Optional[str] = typer.Option(
        None,
        "--model",
        help=(
            "模型 ID。省略时：自定义 model_name > "
            f"{client.MODEL_ENV} > {client.DEFAULT_MODEL}。"
            "OpenRouter 的 typesafe/ 前缀在打 TypeSafe 时会去掉。"
        ),
    ),
    base_url: Optional[str] = typer.Option(
        None,
        "--base-url",
        help=(
            "API 根地址。优先级：该选项 > 自定义 base_url > "
            f"{client.BASE_URL_ENV} > 按 key 自动选择。本地 mock 用这个。"
        ),
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


def _evaluate(
    ctx: typer.Context,
    state: Any,
    questions: Dict[str, Any],
) -> Dict[str, Any]:
    """Call the API and return the raw response."""
    opts = ctx.obj
    return client.evaluate(
        state=state,
        questions=questions,
        api_key=opts["api_key"],
        model=opts["model"],
        base_url=opts["base_url"],
        timeout=opts["timeout"],
    )


def _emit_usage(response: Dict[str, Any]) -> None:
    usage = response.get("usage")
    if not usage:
        return
    typer.echo(
        f"usage: input={usage.get('input_tokens')} tokens, "
        f"output={usage.get('output_tokens')} tokens",
        err=True,
    )


def _run(
    ctx: typer.Context,
    state: Any,
    questions: Dict[str, Any],
    question_id: str,
) -> Dict[str, Any]:
    """Call the API and return the single answer for ``question_id``."""
    response = _evaluate(ctx, state, questions)
    if ctx.obj["json_output"]:
        typer.echo(json.dumps(response, ensure_ascii=False, indent=2))
        raise typer.Exit()

    answer = response.get("answers", {}).get(question_id)
    if answer is None:
        raise client.APIError(f"响应中缺少答案 '{question_id}'：{response}")
    _emit_usage(response)
    return answer


def _classify_items(
    states: Optional[List[str]],
    file: Any,
    json_state: bool,
) -> List[Any]:
    """One state per item. Positionals are separate requests, not one blob."""
    if states and file is not None and len(states) > 1:
        raise typer.BadParameter("多项位置参数与 --file 不能同时使用。")
    if states and file is None:
        items = []
        for raw in states:
            if not raw or not raw.strip():
                raise typer.BadParameter("分类项不能为空。")
            items.append(_resolve_state(raw, None, json_state))
        return items
    return [_resolve_state(None, file, json_state)]

def _display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1 for char in text)


def _pad_display(text: str, width: int) -> str:
    return text + " " * max(width - _display_width(text), 0)


def _item_label(item: Any) -> str:
    if isinstance(item, str):
        return item
    return json.dumps(item, ensure_ascii=False)


def _print_classify(answer: Dict[str, Any]) -> None:
    typer.echo(
        f"分类 (classify): {answer['choice']}  (置信度={answer['confidence']:.4f})"
    )
    typer.echo("各类别概率:")
    ranked = sorted(answer["probabilities"].items(), key=lambda kv: -kv[1])
    for name, prob in ranked:
        typer.echo(f"  {name}: {prob * 100:.1f}%")


def _print_classify_table(rows: List[tuple[str, Dict[str, Any]]]) -> None:
    """One table for every item. Do not repeat the single-item block."""
    prepared: List[tuple[str, str, str, str]] = []
    for item, answer in rows:
        choice = str(answer.get("choice", ""))
        probability = (answer.get("probabilities") or {}).get(answer.get("choice"))
        probability_text = f"{probability * 100:.1f}%" if isinstance(probability, (int, float)) else "-"
        confidence = answer.get("confidence")
        confidence_text = f"{confidence:.4f}" if isinstance(confidence, (int, float)) else "-"
        prepared.append((item, choice, probability_text, confidence_text))
    headers = ("项", "分类", "概率", "置信度")
    widths = [
        max(_display_width(headers[index]), *(_display_width(row[index]) for row in prepared))
        for index in range(4)
    ]

    def format_row(columns: tuple[str, str, str, str]) -> str:
        return "  ".join(
            _pad_display(column, widths[index]) for index, column in enumerate(columns)
        ).rstrip()

    typer.echo(format_row(headers))
    for row in prepared:
        typer.echo(format_row(row))


def _emit_total_usage(responses: List[Dict[str, Any]]) -> None:
    total_input = 0
    total_output = 0
    seen = False
    for response in responses:
        usage = response.get("usage") or {}
        if "input_tokens" in usage or "output_tokens" in usage:
            seen = True
        total_input += usage.get("input_tokens") or 0
        total_output += usage.get("output_tokens") or 0
    if not seen:
        return
    typer.echo(
        f"usage: requests={len(responses)}, input={total_input} tokens, "
        f"output={total_output} tokens",
        err=True,
    )


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
        f"选择 (choice): {answer['choice']}  (置信度={answer['confidence']:.4f})"
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
        f"打分 (score): {answer['score']:.4f}  (置信度={answer['confidence']:.4f})"
    )
    typer.echo("等级概率:")
    legend = answer.get("legend", {})
    for level_key, prob in answer["probabilities"].items():
        desc = legend.get(level_key, level_key)
        typer.echo(f"  [{level_key}] {desc}: {prob:.4f}")


# --------------------------------------------------------------------------- #
# 分类 / classify (derived from choice)
# --------------------------------------------------------------------------- #


@app.command("classify", help="分类：单标签分类。可传入多项，内部逐项请求。")
def classify(
    ctx: typer.Context,
    state: Optional[List[str]] = typer.Argument(None, help="待分类的内容，可多个。每项单独请求。"),
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
        None, "--file", "-f", help="从文件读取一项 state。与多个位置参数不能同时使用。",
    ),
    json_state: bool = typer.Option(
        False, "--json-state", help="将每一项 state 解析为 JSON 对象/数组。",
    ),
) -> None:
    """分类（classify）：由 Choice 衍生的单标签分类。

    内部即一个 ``choice`` 问题，``criteria`` 为各分类标签。多个位置参数会逐项请求，
    不是把它们拼成一份 state。多项的人类可读输出是一张表；单项仍展开各类别概率。
    """
    criteria = _parse_name_value(label, "--label")
    if len(criteria) < 2:
        raise typer.BadParameter("分类至少需要 2 个 --label。")
    items = _classify_items(state, file, json_state)
    questions = {"class": client.choice_question(question, criteria)}
    rendered: List[Dict[str, Any]] = []
    table_rows: List[tuple[str, Dict[str, Any]]] = []
    multiple = len(items) > 1
    for item in items:
        response = _evaluate(ctx, item, questions)
        answer = response.get("answers", {}).get("class")
        if answer is None:
            raise client.APIError(f"响应中缺少答案 'class'：{response}")
        rendered.append({"item": item, "response": response})
        table_rows.append((_item_label(item), answer))
    if ctx.obj["json_output"]:
        if len(rendered) == 1:
            typer.echo(json.dumps(rendered[0]["response"], ensure_ascii=False, indent=2))
        else:
            typer.echo(json.dumps(rendered, ensure_ascii=False, indent=2))
        return
    if multiple:
        _print_classify_table(table_rows)
        _emit_total_usage([entry["response"] for entry in rendered])
        return
    _print_classify(table_rows[0][1])
    _emit_usage(rendered[0]["response"])


def _mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}…{value[-4:]}"


def _prompt_required(label: str, current: str) -> str:
    while True:
        value = typer.prompt(label, default=current).strip() if current else typer.prompt(label).strip()
        if value:
            return value
        typer.echo(f"{label} 不能为空。", err=True)


def _prompt_settings(current: dict[str, str]) -> dict[str, str]:
    path = settings.settings_path()
    typer.echo(f"自定义端点将写入 {path}")
    typer.echo("直接回车保留括号中的当前值。")
    base_url = _prompt_required("Base URL", current.get("base_url", ""))
    existing_key = current.get("api_key", "")
    if existing_key:
        typer.echo(f"API Key 已保存（{_mask_secret(existing_key)}）。直接回车保留，或输入新 key。")
        typed = typer.prompt("API Key", default="", show_default=False).strip()
        api_key = typed or existing_key
    else:
        api_key = _prompt_required("API Key", "")
    model_name = _prompt_required("Model name", current.get("model_name") or client.DEFAULT_MODEL)
    return {"base_url": base_url, "api_key": api_key, "model_name": model_name}


def _print_settings() -> None:
    path = settings.settings_path()
    data = settings.load_settings()
    typer.echo(f"配置文件：{path}")
    if data.get("api_key") and data.get("base_url"):
        typer.echo("状态：已配置，默认使用自定义端点")
        typer.echo(f"  base_url: {data['base_url']}")
        typer.echo(f"  api_key: {_mask_secret(data['api_key'])}")
        model_name = data.get("model_name") or "（未设置，回退 TYPESAFE_MODEL / jev-latest）"
        typer.echo(f"  model_name: {model_name}")
    elif data:
        typer.echo("状态：文件存在，但未同时设置 base_url 与 api_key，不会作为默认端点")
        for key in ("base_url", "api_key", "model_name"):
            if data.get(key):
                shown = _mask_secret(data[key]) if key == "api_key" else data[key]
                typer.echo(f"  {key}: {shown}")
    else:
        typer.echo("状态：未配置自定义端点")
    typer.echo(f"未传 --api-key 时的 key 来源：{client.default_key_source()}")


def _save_setup(merged: dict[str, str]) -> None:
    try:
        path = settings.save_settings(merged)
    except settings.SettingsError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(f"已保存自定义端点：{path}")
    typer.echo(f"  base_url: {merged['base_url']}")
    typer.echo(f"  model_name: {merged['model_name']}")
    typer.echo("之后默认使用该配置；没有它时才用 TYPESAFE_API_KEY，最后才用 OPENROUTER_API_KEY。")


@app.command("setup", help="配置自定义端点（base_url、api_key、model_name）。")
def setup(
    base_url: Optional[str] = typer.Option(None, "--base-url", help="自定义 API 根地址。"),
    api_key: Optional[str] = typer.Option(None, "--api-key", help="自定义 API Key。"),
    model: Optional[str] = typer.Option(None, "--model", help="自定义模型名，写入 model_name。"),
    show: bool = typer.Option(False, "--show", is_flag=True, help="显示已保存的自定义端点，不修改。"),
    clear: bool = typer.Option(False, "--clear", is_flag=True, help="删除自定义端点配置。"),
) -> None:
    """把自定义端点写入 ``~/.config/jev-cli/setting.yaml``。

    配齐后，后续命令默认用它，然后才是 ``TYPESAFE_API_KEY``，最后是
    ``OPENROUTER_API_KEY``。单次调用仍可用全局 ``--api-key`` / ``--base-url`` /
    ``--model`` 覆盖。
    """
    provided = [value for value in (base_url, api_key, model) if value is not None and value.strip()]
    if show and (clear or provided):
        raise typer.BadParameter("--show 只查看，不能同时修改或删除。")
    if clear and provided:
        raise typer.BadParameter("--clear 会删除全部自定义配置，不要同时传入配置项。")
    if show:
        try:
            _print_settings()
        except settings.SettingsError as exc:
            raise typer.BadParameter(str(exc)) from exc
        return
    if clear:
        try:
            removed = settings.clear_settings()
        except settings.SettingsError as exc:
            raise typer.BadParameter(str(exc)) from exc
        path = settings.settings_path()
        if removed:
            typer.echo(f"已删除自定义配置：{path}")
        else:
            typer.echo(f"没有自定义配置：{path}")
        typer.echo("之后按 TYPESAFE_API_KEY、OPENROUTER_API_KEY 的顺序选择。")
        return

    try:
        current = settings.load_settings()
    except settings.SettingsError as exc:
        raise typer.BadParameter(str(exc)) from exc

    if not provided:
        if not sys.stdin.isatty():
            raise typer.BadParameter(
                "非交互环境请传入 --base-url、--api-key、--model，或使用 --show / --clear。"
            )
        _save_setup(_prompt_settings(current))
        return

    merged = dict(current)
    if base_url is not None and base_url.strip():
        merged["base_url"] = base_url.strip()
    if api_key is not None and api_key.strip():
        merged["api_key"] = api_key.strip()
    if model is not None and model.strip():
        merged["model_name"] = model.strip()
    _save_setup(merged)


def main() -> None:
    """CLI 入口。"""
    try:
        app()
    except client.TypeSafeError as exc:
        typer.echo(f"错误: {exc}", err=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
