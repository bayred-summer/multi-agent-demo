"""Friends Bar Phase0：两个 Agent 的最小协作编排器。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from src.friends_bar.agents import AGENTS, normalize_agent_name
from src.invoke import invoke
from src.utils.runtime_config import load_runtime_config

# 当前 Phase0 只支持两个 Agent 的轮转协作。
AGENT_TURN_ORDER = ("玲娜贝儿", "达菲")


def _next_agent(current_name: str) -> str:
    """根据当前 Agent 名称，返回下一个轮到的 Agent。"""
    if current_name == AGENT_TURN_ORDER[0]:
        return AGENT_TURN_ORDER[1]
    return AGENT_TURN_ORDER[0]


def _format_history(transcript: List[Dict[str, Any]]) -> str:
    """把已有转录整理为提示词历史文本。"""
    if not transcript:
        return "（暂无历史对话）"

    lines: List[str] = []
    for item in transcript:
        lines.append(f"第{item['turn']}轮 {item['agent']}：{item['text']}")
    return "\n".join(lines)


def _extract_peer_question(
    transcript: List[Dict[str, Any]],
    current_agent: str,
) -> Optional[str]:
    """从历史中提取“给当前 Agent”的问题行。"""
    if not transcript:
        return None
    markers = (f"发送给{current_agent}：", f"给{current_agent}：")
    # 从最近一次开始反向查找
    for item in reversed(transcript):
        text = item.get("text") or ""
        # 同一条消息里优先取最后一行，避免拿到收件人声明而不是问题。
        for line in reversed(text.splitlines()):
            for marker in markers:
                if marker in line:
                    extracted = line.split(marker, 1)[1].strip()
                    if extracted:
                        return extracted
    return None


def _build_turn_prompt(
    *,
    user_request: str,
    current_agent: str,
    peer_agent: str,
    workdir: str,
    transcript: List[Dict[str, Any]],
    extra_instruction: Optional[str] = None,
) -> str:
    """构建单轮 Agent 调用提示词。"""
    mission = AGENTS[current_agent].mission
    history_text = _format_history(transcript)
    peer_question = _extract_peer_question(transcript, current_agent)
    peer_question_text = (
        f"对方刚才的问题：{peer_question}\n\n" if peer_question else ""
    )
    extra_text = f"\n{extra_instruction}\n" if extra_instruction else ""
    return (
        f"任务目标：{user_request}\n\n"
        f"执行目录：{workdir}\n"
        f"你已在该目录中执行任务，可直接读写文件，不要请求访问权限。\n\n"
        f"当前协作历史：\n{history_text}\n\n"
        f"{peer_question_text}"
        f"你是“{current_agent}”，职责：{mission}\n"
        f"请直接围绕任务作答，禁止解释系统/角色/脚本/运行方式。\n"
        f"禁止输出“无法访问目录”“请授权”“请先提供文件列表”等请求。\n"
        f"不要问好，不要寒暄，不要自我介绍。\n\n"
        f"输出要求：\n"
        f"1) 第一行必须以“发送给{peer_agent}：”开头，说明这条消息的接收方；\n"
        f"2) 如果对方有问题，先回答；\n"
        f"3) 再给出一条明确的协作建议；\n"
        f"4) 最后一行必须以“发送给{peer_agent}：”开头，提出一个明确问题；\n"
        f"5) 控制在 6 句话以内。\n"
        f"{extra_text}"
    )


def run_two_agent_dialogue(
    user_request: str,
    *,
    rounds: Optional[int] = None,
    start_agent: Optional[str] = None,
    project_path: Optional[str] = None,
    use_session: bool = False,
    stream: bool = True,
    timeout_level: Optional[str] = "standard",
    config_path: str = "config.toml",
) -> Dict[str, Any]:
    """运行 Friends Bar 两个 Agent 的轮转协作。

    参数：
    - user_request: 用户输入的任务目标
    - rounds: 总轮次（每轮仅一个 Agent 发言），默认读取 config.toml
    - start_agent: 首轮发言的 Agent（支持中文名与 provider 别名），默认读取 config.toml
    - project_path: agent 任务执行目录；为空时使用当前工作目录
    - use_session: 是否复用 CLI session（默认关闭，保证单次演示隔离）
    - stream: 是否实时打印每轮结果
    - timeout_level: 调用超时档位（quick/standard/complex）
    - config_path: 配置文件路径
    """
    if not isinstance(user_request, str) or not user_request.strip():
        raise ValueError("user_request must be a non-empty string")
    runtime_config = load_runtime_config(config_path=config_path)
    friends_bar_config = runtime_config.get("friends_bar", {})

    resolved_rounds = (
        int(friends_bar_config.get("default_rounds", 4))
        if rounds is None
        else int(rounds)
    )
    if resolved_rounds < 1:
        raise ValueError("rounds must be >= 1")

    resolved_start_agent = (
        str(friends_bar_config.get("start_agent", "玲娜贝儿"))
        if start_agent is None
        else start_agent
    )
    resolved_workdir = str(Path.cwd()) if project_path is None else str(Path(project_path))
    if not Path(resolved_workdir).exists():
        raise ValueError(f"project_path does not exist: {resolved_workdir}")
    if not Path(resolved_workdir).is_dir():
        raise ValueError(f"project_path is not a directory: {resolved_workdir}")

    current_agent = normalize_agent_name(resolved_start_agent)
    transcript: List[Dict[str, Any]] = []

    for turn in range(1, resolved_rounds + 1):
        peer_agent = _next_agent(current_agent)
        adjusted_prompt = _build_turn_prompt(
            user_request=user_request,
            current_agent=current_agent,
            peer_agent=peer_agent,
            workdir=resolved_workdir,
            transcript=transcript,
        )
        result = invoke(
            current_agent,
            adjusted_prompt,
            use_session=use_session,
            stream=False,
            workdir=resolved_workdir,
            timeout_level=timeout_level,
        )

        text = (result.get("text") or "").strip()
        if not text:
            text = "（空回复）"

        turn_record = {
            "turn": turn,
            "agent": current_agent,
            "provider": result.get("cli"),
            "text": text,
            "session_id": result.get("session_id"),
            "elapsed_ms": result.get("elapsed_ms"),
        }
        transcript.append(turn_record)

        if stream:
            print(f"\n[{current_agent} -> {peer_agent}]")
            print(text)

        current_agent = peer_agent

    return {
        "workspace": "Friends Bar",
        "user_request": user_request,
        "rounds": resolved_rounds,
        "turns": transcript,
    }
