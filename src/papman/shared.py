from pathlib import Path
from typing import Iterable

from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Static, Button, Input, DirectoryTree
from textual.app import Binding, ComposeResult
from textual.message import Message
from textual import on


class MessageScreen(ModalScreen):
    BINDINGS = [
        Binding("q", "dismiss_modal", "Close", show=False),
        Binding("escape", "dismiss_modal", "Close", show=False),
        Binding("enter", "dismiss_modal", "Close", show=False),
    ]

    def __init__(self, msg, is_error=False):
        self.msg = msg
        self.is_error = is_error
        super().__init__(classes="modal")

    def compose(self):
        classes = "dialog-content"
        if self.is_error:
            classes += " error"
        with Vertical(classes=classes):
            yield Static(self.msg)

    def action_dismiss_modal(self):
        self.dismiss(None)


class InputScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close", show=False),
    ]

    def __init__(self, msg: str | None = None, placeholder: str = "", callback=None):
        self.msg = msg
        self.placeholder = placeholder
        self.callback = callback
        super().__init__(classes="modal")

    def compose(self):
        with Vertical(classes="dialog-content"):
            if self.msg:
                yield Static(self.msg)
            yield Input(placeholder=self.placeholder, classes="input")

    def action_dismiss_modal(self):
        self.dismiss(None)

    @on(Input.Submitted, ".input")
    def action_submit(self):
        input_value = self.query_one(Input).value
        if self.callback is not None:
            self.callback(input_value)
        self.dismiss(input_value)


class ConfirmScreen(ModalScreen):
    BINDINGS = [
        Binding("q", "dismiss_modal", "Close", show=False),
        Binding("escape", "dismiss_modal", "Close", show=False),
        Binding("enter", "confirm", "Confirm", show=False),
    ]

    def __init__(self, msg: str):
        self.msg = msg
        super().__init__(classes="modal")

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog-content"):
            yield Static(self.msg)
            with Horizontal():
                yield Button("Confirm", id="confirm-btn", variant="primary")
                yield Button("Cancel", id="cancel-btn")

    def action_dismiss_modal(self):
        self.dismiss(False)

    def action_confirm(self):
        self.dismiss(True)

    @on(Button.Pressed, "#confirm-btn")
    def on_confirm_pressed(self):
        self.dismiss(True)

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel_pressed(self):
        self.dismiss(False)


class FilteredDirectoryTree(DirectoryTree):
    class FileChosen(Message):
        bubble: bool = True

        def __init__(self, tree: "FilteredDirectoryTree", path: Path) -> None:
            self._tree = tree
            self.path = path
            super().__init__()

    BINDINGS = [
        Binding("enter", "select_cursor", "Select"),
        Binding("escape", "on_escape", "Close"),
        Binding("j", "cursor_down", "Down"),
        Binding("k", "cursor_up", "Up"),
    ]

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        return [path for path in paths if not path.name.startswith(".")]

    def action_select_cursor(self):
        node = self.cursor_node
        if node.allow_expand:
            node.expand()
        else:
            msg = self.FileChosen(self, node.data.path)
            self.post_message(msg)
        return
