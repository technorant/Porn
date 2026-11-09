"""Small terminal UI: keyboard menus, panels and live progress, with plain fallbacks."""
import os
import re
import shutil
import sys
import textwrap
import threading
import time
from dataclasses import dataclass


def enable_terminal():
    if os.name == "nt" and sys.stdout.isatty():
        try:
            import ctypes
            kernel = ctypes.windll.kernel32
            handle = kernel.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            if kernel.GetConsoleMode(handle, ctypes.byref(mode)):
                return bool(kernel.SetConsoleMode(handle, mode.value | 4))
        except (AttributeError, OSError):
            return False
    return sys.stdout.isatty() and os.getenv("TERM") != "dumb"


def read_key():
    if os.name == "nt":
        import msvcrt
        key = msvcrt.getwch()
        if key in ("\x00", "\xe0"):
            return {"H": "up", "P": "down"}.get(msvcrt.getwch(), "")
    else:
        import select
        import termios
        import tty
        fd = sys.stdin.fileno()
        settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            key = os.read(fd, 1).decode("utf-8", errors="replace")
            if key == "\x1b":
                sequence = ""
                while len(sequence) < 2 and select.select([fd], [], [], 0.05)[0]:
                    sequence += os.read(fd, 1).decode("ascii", errors="ignore")
                return {"[A": "up", "[B": "down"}.get(sequence, "escape")
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, settings)
    if key == "\x03":
        raise KeyboardInterrupt
    if key == "\x04":
        raise EOFError
    return {"\r": "enter", "\n": "enter", "\x1b": "escape"}.get(key, key)


def clean(value):
    """Keep terminal control sequences out of remote/user-provided labels."""
    value = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "", str(value))
    value = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", value)
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", " ", value)


@dataclass(frozen=True)
class Choice:
    value: str
    label: str
    detail: str = ""


class Console:
    COLORS = {"cyan": "96", "gold": "93", "green": "92", "red": "91", "muted": "90", "bold": "1"}

    def __init__(self):
        self.terminal = enable_terminal()
        self.color = self.terminal and "NO_COLOR" not in os.environ

    @property
    def width(self):
        return max(24, min(88, shutil.get_terminal_size((88, 24)).columns - 2))

    def paint(self, text, color):
        text = str(text)
        return f"\033[{self.COLORS[color]}m{text}\033[0m" if self.color else text

    def say(self, text="", color=None):
        text = clean(text)
        print(self.paint(text, color) if color else text, flush=True)

    def panel(self, title, lines=(), color="cyan"):
        width = self.width
        self.say("+" + "-" * (width - 2) + "+", color)
        for line in (title, *lines):
            for chunk in textwrap.wrap(clean(line), width - 6) or [""]:
                self.say("|  " + chunk.ljust(width - 6) + "  |", color if line == title else None)
        self.say("+" + "-" * (width - 2) + "+", color)

    def banner(self, repo="", completed=0, pending=0, configured=False):
        self.say()
        self.say("    /\\     G I T H U B", "cyan")
        self.say("   /++\\    A C H I E V E M E N T", "gold")
        self.say("   \\++/    P Y T H O N   /   0.2", "muted")
        self.say()
        self.panel(repo or "Connect your repository", [
            f"Credentials: {'configured' if configured else 'setup needed'}   /   Completed: {completed}   /   To inspect: {pending}",
            "Choose a badge. Follow the workflow. Check your GitHub profile.",
        ])

    def choose(self, title, choices, *, default=0):
        self.say()
        self.say(title, "bold")
        if not self.terminal or not sys.stdin.isatty():
            for i, choice in enumerate(choices, 1):
                self.say(f"  {i}. {choice.label}" + (f"  /  {choice.detail}" if choice.detail else ""))
            while True:
                value = input(f"Select [1-{len(choices)}, default {default + 1}]: ").strip()
                if not value:
                    return choices[default].value
                if value.isdigit() and 1 <= int(value) <= len(choices):
                    return choices[int(value) - 1].value
                self.say("Choose a number from the menu.", "gold")
        selected, height = default, 0
        print("\033[?25l", end="", flush=True)
        try:
            while True:
                if height:
                    print(f"\033[{height}A", end="")
                for i, choice in enumerate(choices):
                    label = f" {'>' if i == selected else ' '} {i + 1:>2}  {choice.label}"
                    if choice.detail:
                        label += f"  /  {choice.detail}"
                    label = clean(label)[:self.width - 1]
                    print("\r\033[2K" + self.paint(label, "cyan" if i == selected else "muted"))
                print("\r\033[2K" + self.paint("  Up/Down or j/k  |  Enter select  |  Esc back", "muted"), flush=True)
                height = len(choices) + 1
                key = read_key()
                if key in ("up", "k"):
                    selected = (selected - 1) % len(choices)
                elif key in ("down", "j"):
                    selected = (selected + 1) % len(choices)
                elif key == "enter":
                    return choices[selected].value
                elif key in ("escape", "q"):
                    return "back"
                elif key.isdigit() and 1 <= int(key) <= len(choices):
                    return choices[int(key) - 1].value
        finally:
            print("\033[?25h", end="", flush=True)

    def ask(self, label, default="", *, required=False, validator=None):
        while True:
            suffix = f" [{clean(default)}]" if default else ""
            value = input(f"  {label}{suffix}: ").strip() or default
            if required and not value:
                self.say("This field is required.", "gold")
                continue
            if validator:
                try:
                    validator(value)
                except ValueError as exc:
                    self.say(str(exc), "gold")
                    continue
            return value

    def activity(self, message):
        return Activity(self, message)

    def progress(self, current, total):
        width = 22
        filled = int(width * current / total) if total else width
        self.say(f"  [{'#' * filled}{'.' * (width - filled)}]  {current}/{total}", "cyan")


class Activity:
    def __init__(self, console, message):
        self.console, self.message = console, clean(message)
        self.stop = threading.Event()
        self.thread = None

    def update(self, message):
        self.message = clean(message)
        if not self.console.terminal:
            self.console.say("  > " + self.message)

    def __enter__(self):
        self.started = time.monotonic()
        if self.console.terminal:
            self.thread = threading.Thread(target=self._animate, daemon=True)
            self.thread.start()
        else:
            self.console.say("  > " + self.message)
        return self

    def _animate(self):
        index = 0
        frames = "|/-\\"
        while not self.stop.is_set():
            elapsed = int(time.monotonic() - self.started)
            text = f"  {frames[index % 4]} {self.message}  {elapsed}s"[:self.console.width - 1]
            print("\r\033[2K" + self.console.paint(text, "cyan"), end="", flush=True)
            index += 1
            self.stop.wait(0.1)

    def __exit__(self, *args):
        self.stop.set()
        if self.thread:
            self.thread.join()
            print("\r\033[2K", end="", flush=True)
