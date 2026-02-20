"""CLI 子进程运行器。

提供生产可用所需的关键能力：
1. stdout/stderr 双通道活跃心跳
2. 空闲超时与总超时
3. 超时后优雅终止（TERM -> 等待 -> KILL）
4. 父进程信号与退出清理
5. 结构化错误信息（便于调试和重试判断）
"""

from __future__ import annotations

import atexit
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class TimeoutConfig:
    """超时配置。"""

    idle_timeout_s: float
    max_timeout_s: float
    terminate_grace_s: float = 5.0


@dataclass(frozen=True)
class ProcessResult:
    """子进程运行结果。"""

    return_code: int
    elapsed_ms: int
    stderr_lines: List[str]
    terminated_reason: Optional[str]
    command_repr: str


class ProcessExecutionError(RuntimeError):
    """子进程执行异常（带结构化上下文）。"""

    def __init__(
        self,
        *,
        provider: str,
        reason: str,
        command_repr: str,
        elapsed_ms: int,
        return_code: Optional[int] = None,
        stderr_lines: Optional[List[str]] = None,
        session_id: Optional[str] = None,
        extra_message: Optional[str] = None,
    ) -> None:
        self.provider = provider
        self.reason = reason
        self.command_repr = command_repr
        self.elapsed_ms = elapsed_ms
        self.return_code = return_code
        self.stderr_lines = stderr_lines or []
        self.session_id = session_id
        self.extra_message = extra_message
        super().__init__(self._build_message())

    @property
    def stderr_tail(self) -> List[str]:
        """返回 stderr 尾部片段，避免日志过长。"""
        return self.stderr_lines[-20:]

    def _build_message(self) -> str:
        base = (
            f"[{self.provider}] process failed: reason={self.reason}, "
            f"elapsed_ms={self.elapsed_ms}, return_code={self.return_code}, "
            f"session_id={self.session_id or 'n/a'}, command={self.command_repr}"
        )
        if self.extra_message:
            base = f"{base}, detail={self.extra_message}"
        if self.stderr_tail:
            base = f"{base}, stderr_tail={' | '.join(self.stderr_tail)}"
        return base


TIMEOUT_PROFILES: Dict[str, TimeoutConfig] = {
    # 适合短问答、轻量任务
    "quick": TimeoutConfig(idle_timeout_s=60, max_timeout_s=300, terminate_grace_s=3),
    # 通用默认：5 分钟无输出超时，总 30 分钟
    "standard": TimeoutConfig(
        idle_timeout_s=300, max_timeout_s=1800, terminate_grace_s=5
    ),
    # 适合复杂任务：15 分钟无输出超时，总 60 分钟
    "complex": TimeoutConfig(
        idle_timeout_s=900, max_timeout_s=3600, terminate_grace_s=8
    ),
}


def resolve_timeout_config(
    *,
    timeout_level: str,
    idle_timeout_s: Optional[float],
    max_timeout_s: Optional[float],
    terminate_grace_s: Optional[float],
) -> TimeoutConfig:
    """按“任务级配置 + 显式覆盖”生成最终超时配置。"""
    base = TIMEOUT_PROFILES.get(timeout_level, TIMEOUT_PROFILES["standard"])
    return TimeoutConfig(
        idle_timeout_s=idle_timeout_s if idle_timeout_s is not None else base.idle_timeout_s,
        max_timeout_s=max_timeout_s if max_timeout_s is not None else base.max_timeout_s,
        terminate_grace_s=(
            terminate_grace_s
            if terminate_grace_s is not None
            else base.terminate_grace_s
        ),
    )


def _build_command_repr(
    command: str,
    args: List[str],
    workdir: Optional[str],
    *,
    max_chars: int = 800,
) -> str:
    """Build compact command text for logs/errors.

    Large prompts can make error logs unreadable and increase mojibake risk in
    non-UTF-8 terminals, so we keep a bounded representation.
    """
    joined = " ".join([command, *args])
    if len(joined) > max_chars:
        overflow = len(joined) - max_chars
        joined = f"{joined[:max_chars]} ...<truncated {overflow} chars>"
    if workdir:
        joined = f"{joined} (cwd={workdir})"
    return joined


def _drain_text_stream(
    stream,
    source: str,
    output_queue: "queue.Queue[Tuple[str, str]]",
    bump_activity: Callable[[], None],
    stop_event: threading.Event,
) -> None:
    """按 chunk 读取文本流并切行为 line。

    这样可以处理：
    - 不完整行（半包）：放入 buffer，等待下一块
    - 一块中多行（粘包）：循环按换行切分
    """
    buffer = ""
    while not stop_event.is_set():
        chunk = stream.read(4096)
        if chunk == "":
            break
        bump_activity()
        buffer += chunk
        while True:
            idx = buffer.find("\n")
            if idx < 0:
                break
            line = buffer[:idx].rstrip("\r")
            buffer = buffer[idx + 1 :]
            output_queue.put((source, line))

    # EOF 时把尾部残留行也提交出去。
    if buffer:
        output_queue.put((source, buffer.rstrip("\r")))


def run_stream_process(
    *,
    provider: str,
    command: str,
    args: List[str],
    workdir: Optional[str],
    env: Optional[Dict[str, str]] = None,
    timeout: TimeoutConfig,
    stream_stderr: bool,
    stderr_prefix: str,
    on_stdout_line: Callable[[str], None],
    on_process_start: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_first_byte: Optional[Callable[[Dict[str, Any]], None]] = None,
    inherit_stdin: bool = False,
) -> ProcessResult:
    """运行一个流式 CLI 子进程。"""
    command_repr = _build_command_repr(command, args, workdir)
    start = time.monotonic()
    last_activity = start
    activity_lock = threading.Lock()
    stop_event = threading.Event()
    line_queue: "queue.Queue[Tuple[str, str]]" = queue.Queue()
    stderr_lines: List[str] = []
    terminated_reason: Optional[str] = None
    process: Optional[subprocess.Popen] = None
    first_byte_emitted = False

    def elapsed_ms() -> int:
        return int((time.monotonic() - start) * 1000)

    def bump_activity() -> None:
        nonlocal last_activity
        with activity_lock:
            last_activity = time.monotonic()

    def get_last_activity() -> float:
        with activity_lock:
            return last_activity

    def terminate_process(reason: str) -> None:
        nonlocal terminated_reason
        if process is None or process.poll() is not None:
            return
        terminated_reason = reason
        try:
            process.terminate()
        except Exception:
            pass

        deadline = time.monotonic() + timeout.terminate_grace_s
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return
            time.sleep(0.05)

        if process.poll() is None:
            try:
                process.kill()
            except Exception:
                pass

    signal_received: Dict[str, Optional[int]] = {"code": None}

    def signal_handler(signum, _frame) -> None:
        signal_received["code"] = int(signum)
        stop_event.set()
        terminate_process("parent_signal")

    previous_handlers = {}
    for signal_name in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, signal_name, None)
        if sig is None:
            continue
        try:
            previous_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, signal_handler)
        except ValueError:
            # 非主线程或平台不支持时忽略，不阻断主逻辑。
            continue

    def atexit_cleanup() -> None:
        terminate_process("parent_exit")

    atexit.register(atexit_cleanup)

    try:
        try:
            process = subprocess.Popen(
                [command, *args],
                stdin=None if inherit_stdin else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=workdir,
                env=env,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=0,
            )
        except FileNotFoundError as exc:
            raise ProcessExecutionError(
                provider=provider,
                reason="launch_error",
                command_repr=command_repr,
                elapsed_ms=elapsed_ms(),
                extra_message=str(exc),
            ) from exc

        assert process.stdout is not None
        assert process.stderr is not None

        if on_process_start:
            try:
                on_process_start(
                    {
                        "provider": provider,
                        "pid": process.pid,
                        "command_repr": command_repr,
                        "command": command,
                        "args": list(args),
                        "workdir": workdir,
                        "elapsed_ms": elapsed_ms(),
                    }
                )
            except Exception:
                # Logging hooks must not break main flow.
                pass

        stdout_thread = threading.Thread(
            target=_drain_text_stream,
            args=(process.stdout, "stdout", line_queue, bump_activity, stop_event),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=_drain_text_stream,
            args=(process.stderr, "stderr", line_queue, bump_activity, stop_event),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        while True:
            # 优先消费队列，防止积压。
            try:
                source, line = line_queue.get(timeout=0.1)
            except queue.Empty:
                source = ""
                line = ""

            if source:
                if not first_byte_emitted and on_first_byte:
                    first_byte_emitted = True
                    try:
                        on_first_byte(
                            {
                                "provider": provider,
                                "source": source,
                                "elapsed_ms": elapsed_ms(),
                            }
                        )
                    except Exception:
                        pass
                if source == "stderr":
                    if line.strip():
                        stderr_lines.append(line.strip())
                        if stream_stderr:
                            print(f"{stderr_prefix}{line.strip()}", file=sys.stderr)
                else:
                    try:
                        on_stdout_line(line)
                    except Exception as exc:
                        terminate_process("callback_error")
                        raise ProcessExecutionError(
                            provider=provider,
                            reason="callback_error",
                            command_repr=command_repr,
                            elapsed_ms=elapsed_ms(),
                            return_code=process.poll() if process is not None else None,
                            stderr_lines=stderr_lines,
                            extra_message=str(exc),
                        ) from exc

            now = time.monotonic()
            idle_for = now - get_last_activity()
            running = process.poll() is None

            if running and idle_for > timeout.idle_timeout_s:
                terminate_process("idle_timeout")
            if running and (now - start) > timeout.max_timeout_s:
                terminate_process("max_timeout")

            if not running and line_queue.empty() and not stdout_thread.is_alive() and not stderr_thread.is_alive():
                break

        return_code = process.wait()
        stop_event.set()
        stdout_thread.join(timeout=1.0)
        stderr_thread.join(timeout=1.0)

        result = ProcessResult(
            return_code=return_code,
            elapsed_ms=elapsed_ms(),
            stderr_lines=stderr_lines,
            terminated_reason=terminated_reason,
            command_repr=command_repr,
        )

        if terminated_reason is not None:
            raise ProcessExecutionError(
                provider=provider,
                reason=terminated_reason,
                command_repr=command_repr,
                elapsed_ms=result.elapsed_ms,
                return_code=result.return_code,
                stderr_lines=result.stderr_lines,
            )

        if return_code != 0:
            raise ProcessExecutionError(
                provider=provider,
                reason="nonzero_exit",
                command_repr=command_repr,
                elapsed_ms=result.elapsed_ms,
                return_code=result.return_code,
                stderr_lines=result.stderr_lines,
            )

        return result

    finally:
        stop_event.set()
        if process is not None and process.poll() is None:
            terminate_process("cleanup")
            try:
                process.wait(timeout=2.0)
            except Exception:
                pass

        try:
            atexit.unregister(atexit_cleanup)
        except Exception:
            pass

        for sig, previous in previous_handlers.items():
            try:
                signal.signal(sig, previous)
            except Exception:
                pass
