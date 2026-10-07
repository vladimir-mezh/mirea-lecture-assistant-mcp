from __future__ import annotations

import argparse
import os
from contextlib import asynccontextmanager
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from . import __version__
from .backend import Backend

DUTY_PROMPT = """Ты — ИИ-дежурный приложения MIREA Lecture Assistant на компьютере студента.
Проверь, что приложение работает на текущей паре, и почини, если нет. Пользуйся только
инструментами этого MCP-сервера.

1. Вызови check_health. Если verdict равен "ok" — ответь «OK» и сразу закончи, ничего
   больше не делай: так проверка почти ничего не стоит.
2. Если network.verdict равен "vpn_suspected" — чинить приложение бесполезно: вызови
   get_vpn_help и коротко, простыми словами скажи пользователю, что сделать с VPN.
   Если "offline" — скажи, что нет интернета.
3. Иначе бери проблемы из problems по порядку и вызывай repair с действием из её actions.
   После каждого действия вызывай wait_and_check (60–90 секунд). Не больше пяти действий.
   Если починка выключена, попроси пользователя включить «Разрешить ИИ чинить приложение»
   на вкладке MCP.
4. В конце вызови report_fix: 3–6 строк по-русски, что было, что сделал и помогло ли;
   fixed — true, если check_health в итоге "ok".

Не проси и не трогай пароли, коды из писем, QR-коды и чат лекции."""

WATCH_PROMPT = """Настрой дежурство за MIREA Lecture Assistant на сегодня.

1. Вызови get_schedule и выбери сегодняшние пары.
2. Для каждой пары создай две разовые отложенные задачи своими средствами (если ты умеешь
   создавать отложенные или запланированные задачи): через 5 и через 20 минут после
   начала пары, по местному времени компьютера. Название: «МИРЭА: проверка ЧЧ:ММ».
3. Текст каждой задачи — инструкция дежурного: вызвать check_health; если verdict "ok" —
   ответить «OK» и закончить без лишних действий; иначе действовать по инструкции
   duty_check этого сервера (починка через repair, проверка через wait_and_check,
   отчёт через report_fix).
4. Покажи пользователю список созданных проверок и напомни: компьютер не должен спать.

Если создавать отложенные задачи ты не умеешь, скажи об этом. Предложи включить
«ИИ-дежурного» на вкладке MCP в приложении: тогда приложение само проверяет пары и
зовёт Codex или Claude Code только при сбое."""


def create_server(backend: Backend):
    @asynccontextmanager
    async def lifespan(_server):
        backend.start()
        try:
            yield {}
        finally:
            backend.stop()

    mcp = FastMCP("MIREA Lecture Assistant MCP", lifespan=lifespan,
                  instructions="Diagnose, repair and configure the local MIREA Lecture "
                  "Assistant. Start any check with check_health; if it is ok, stop there. "
                  "Repairs need the app's own permission. Ask before changing settings or "
                  "subject rules. Credentials are entered by the user in the app; there are no "
                  "QR, attendance, chat, shell or credential tools. Prompts: duty_check (one "
                  "check-and-repair round), setup_lecture_watch (schedule checks for today).")

    @mcp.tool()
    def get_status() -> dict:
        """Read application version and scanner state without logging in or submitting anything."""
        return backend.call("status", tool=True)

    @mcp.tool()
    def get_settings() -> dict:
        """Read non-secret settings and their validation schema. No credentials or email codes."""
        return backend.call("get_settings", tool=True)

    @mcp.tool()
    def get_schedule() -> dict:
        """Read cached schedule, without refreshing websites or opening lectures."""
        return backend.call("get_schedule", tool=True)

    @mcp.tool()
    def get_subject_rules() -> dict:
        """Read AUTO/ASK/IGNORE rules for subjects in the cached schedule."""
        return backend.call("get_subject_rules", tool=True)

    @mcp.tool()
    def update_settings(settings: dict) -> dict:
        """Apply only settings listed by get_settings. Requires explicit app-side write permission
        and no unsaved UI edits. Ask the user first. Changes take effect in the running app.
        """
        return backend.call("update_settings", {"settings": settings}, tool=True)

    @mcp.tool()
    def set_subject_rule(subject: str, mode: str) -> dict:
        """Set AUTO/ASK/IGNORE for an existing subject, only at user's request and with app-side
        permission. AUTO affects future lecture opening; never change attendance rules silently.
        """
        return backend.call("set_subject_rule", {"subject": subject, "mode": mode}, tool=True)

    @mcp.tool()
    def check_health() -> dict:
        """Is the app working right now? Returns verdict "ok" or "problem", each problem with
        repair actions, the current pair, and a network check (MIREA sites, internet, VPN)
        when something is wrong. Call this first; if ok, nothing else is needed.
        """
        return backend.call("check_health", tool=True, timeout=30)

    @mcp.tool()
    def wait_and_check(seconds: int = 60) -> dict:
        """Wait 0–120 seconds (a repair takes a minute or so), then check_health again."""
        return backend.call("wait_and_check", {"seconds": seconds}, tool=True,
                            timeout=seconds + 35)

    @mcp.tool()
    def repair(action: str) -> dict:
        """Start one repair from a problem's actions: retry_login, refresh_schedule,
        reopen_lecture, restart_browser or start_scanner. Needs the user's «Разрешить ИИ чинить
        приложение» permission in the app. Check the result with wait_and_check.
        """
        return backend.call("repair", {"action": action}, tool=True)

    @mcp.tool()
    def get_recent_problems() -> dict:
        """Latest warnings and errors of the app's log: time, level, module, event name only."""
        return backend.call("get_recent_problems", tool=True)

    @mcp.tool()
    def get_attendance_history() -> dict:
        """Recent QR events and the pairs where attendance was marked (no QR contents)."""
        return backend.call("get_attendance_history", tool=True)

    @mcp.tool()
    def get_vpn_help() -> dict:
        """How to let MIREA and MTS Link bypass the user's VPN, with ready files; also shows
        the instructions in the app. Use when check_health says vpn_suspected.
        """
        return backend.call("get_vpn_help", tool=True)

    @mcp.tool()
    def report_fix(summary: str, fixed: bool) -> dict:
        """Finish a repair round: 3–6 lines in Russian on what was wrong, what you did and
        whether it helped. The app removes personal data and sends it to the developer.
        """
        return backend.call("report_fix", {"summary": summary, "fixed": fixed}, tool=True)

    @mcp.prompt(title="Проверить и починить приложение")
    def duty_check() -> str:
        """One check-and-repair round of MIREA Lecture Assistant."""
        return DUTY_PROMPT

    @mcp.prompt(title="Дежурство на сегодняшних парах")
    def setup_lecture_watch() -> str:
        """Schedule checks at +5 and +20 minutes of every pair today."""
        return WATCH_PROMPT

    return mcp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", type=Path,
                        default=Path(os.environ.get("LOCALAPPDATA", ".")) / "MireaLectureAssistant")
    parser.add_argument("--client-name", default="MCP-клиент")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args()
    server = create_server(Backend(args.profile, args.client_name))
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
