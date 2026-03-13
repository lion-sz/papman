from pathlib import Path
from typing import Iterable

from textual import events, on, work
from textual.containers import Vertical, Horizontal
from textual.screen import ModalScreen
from textual.widgets import (
    Static,
    Button,
    Input,
    DirectoryTree,
    Footer,
    ListView,
    ListItem,
    Tree,
)
from textual.app import Binding, ComposeResult
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.timer import Timer


class CommandLine(Widget):
    DEFAULT_CSS = """
    CommandLine {
        dock: bottom;
        height: 1;
        width: 100%;
    }
    """

    command = reactive("")

    def render(self):
        return self.command


class VimNavElem:
    can_focus = True
    command: str

    KNONW_COMMANDS = ["j", "k"]
    searchable: bool = False

    _search_mode: bool
    _search_timer: Timer | None
    _before_search_index: int | None
    _is_filtered: bool

    def move(self, steps: int, up: bool):
        raise NotImplementedError()

    def _run_search(self, query: str):
        raise NotImplementedError()

    def _reset_search(self):
        raise NotImplementedError()

    async def _on_key(self, event: events.Key) -> None:
        cl = self.query_one(CommandLine)

        if self.searchable:
            if event.key == "escape" and (self._search_mode or self._is_filtered):
                event.stop()
                self._search_mode = False
                self._is_filtered = False
                if self._search_timer is not None:
                    self._search_timer.stop()
                    self._search_timer = None
                await self._reset_search()
                self.command = ""
                cl.command = ""
                cl.display = False
                return

            if self._search_mode:
                event.stop()
                if self._search_timer is not None:
                    self._search_timer.stop()
                if event.key == "enter":
                    self._search_mode = False
                    self._search_timer = None
                    self._run_search(self.command)
                else:
                    if event.key == "backspace":
                        self.command = (
                            self.command[:-1] if self.command else self.command
                        )
                    else:
                        self.command = (
                            self.command + event.character
                            if event.character
                            else self.command
                        )
                    cl.command = "/" + self.command
                    self._search_timer = self.set_timer(
                        0.2, lambda: self._run_search(self.command)
                    )
                return

            if event.key == "slash":
                event.stop()
                self._before_search_index = self.index
                self._is_filtered = True
                self._search_mode = True
                self.command = ""
                cl.command = "/"
                cl.display = True
                return

        handled = await self.handle_key(event)
        if not handled and not self._is_bound_in_active_chain(event):
            await self.on_unbound_key(event)

    def _is_bound_in_active_chain(self, event: events.Key) -> bool:
        try:
            binding_chain = self.screen._modal_binding_chain
        except Exception:
            return False

        for key in event.aliases:
            if any(key in bindings.key_to_bindings for _, bindings in binding_chain):
                return True

        return False

    async def on_unbound_key(self, event: events.Key) -> None:
        """Hook for keys that don't resolve to a binding on this list view."""
        cl = self.query_one(CommandLine)
        if event.key not in self.KNOWN_COMMANDS:
            if event.key == "backspace":
                self.command = self.command[:-1] if self.command else self.command
            else:
                self.command = self.command + event.key
            cl.command = self.command
            if not cl.display:
                cl.display = True
            return
        # Try parsing the modifier
        if self.command is not None and self.command.isnumeric():
            modifier = int(self.command)
        else:
            modifier = 1
        self.command = ""
        cl.command = ""
        cl.display = False

        if event.key in ("j", "k"):
            self.move(modifier, event.key == "k")
        if event.key == "escape":
            pass
        return


class VimNavList(VimNavElem, Static):
    can_focus = True
    command: str
    elems: list[ListItem]

    KNOWN_COMMANDS = ["j", "k", "escape"]
    searchable: bool = False

    _search_mode: bool
    _search_timer: Timer | None
    _before_search_index: int | None
    _is_filtered: bool

    def __init__(self, *children, **kwargs):
        super().__init__(**kwargs)
        self.elems = children
        self.command = ""
        self._search_mode = False
        self._search_timer = None
        self._before_search_index = None
        self._is_filtered = False

    @property
    def index(self):
        return self.query_one(ListView).index

    @index.setter
    def index(self, value: int):
        self.query_one(ListView).index = value

    def focus(self):
        list_view = self.query_one(ListView)
        if list_view.index is None and len(list_view.children) > 0:
            list_view.index = 0
        return list_view.focus()

    @property
    def highlighted_child(self):
        return self.query_one(ListView).highlighted_child

    def compose(self):
        yield ListView(*self.elems, id=self.id)
        command = CommandLine()
        command.display = False
        yield command

    def run_search(self, query: str) -> list[ListItem]:
        self.app.push_screen(MessageScreen(f"Searching for '{str}'"))
        return

    @work(exclusive=True)
    async def _run_search(self, query: str):
        filtered = self.run_search(query)
        list = self.query_one(ListView)
        await list.clear()
        if len(filtered) > 0:
            await list.extend(filtered)
            list.index = 0
            list.focus()
        else:
            # Keep key handling on the container active when the list has no rows.
            super().focus()
        return

    async def _reset_search(self):
        list = self.query_one(ListView)
        await list.clear()
        await list.extend(self.elems)
        list.index = self._before_search_index
        list.focus()

    def move(self, steps: int, up: bool):
        list = self.query_one(ListView)
        ind = list.index
        n_items = len(list.children)
        if up:
            steps = -steps
        new_ind = ind + steps
        new_ind = max(0, min(new_ind, n_items - 1))
        list.index = new_ind
        return


class VimNavTree(VimNavElem, Static):
    can_focus = True
    command: str
    elems: list[ListItem]

    KNOWN_COMMANDS = ["j", "k", "escape"]
    searchable: bool = False

    _tree: Tree
    _cl: CommandLine

    _search_mode: bool
    _search_timer: Timer | None
    _before_search_index: int | None
    _is_filtered: bool

    def __init__(self, *items, **kwargs):
        super().__init__(*items, **kwargs)
        self.command = ""
        self._search_mode = False
        self._search_timer = None
        self._before_search_index = None
        self._is_filtered = False

    def compose(self):
        self._tree = self.build_tree()
        yield self._tree
        self._cl = CommandLine()
        self._cl.display = False
        yield self._cl

    def focus(self):
        self.query_one(Tree).focus()

    @property
    def cursor_line(self):
        return self._tree.cursor_line

    @cursor_line.setter
    def set_cursor_line(self, value: int):
        self._tree.cursor_line = value

    @property
    def cursor_node(self):
        self._tree.cursor_node

    def move(self, steps: int, up: bool):
        pos = self._tree.cursor_line
        if up:
            steps = -steps
        self._tree.cursor_line = pos + steps
        return


class FilteredDirTree(DirectoryTree):
    file_types: list[str] | None
    search_term: str

    def __init__(self, path: str, file_types: list[str] | None = None, **kwargs):
        super().__init__(path, **kwargs)
        self.file_types = file_types
        self.search_term = ""

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        p = [path for path in paths if not path.name.startswith(".")]
        if self.file_types is not None:
            p = [path for path in p if path.suffix in self.file_types or path.is_dir()]
        if self.search_term:
            p = [
                path
                for path in p
                if self.search_term.lower() in path.name.lower() or path.is_dir()
            ]
        return p


class VimNavDirTree(VimNavElem, Static):
    class FileChosen(Message):
        bubble: bool = True

        def __init__(self, tree: "FilteredDirTree", path: Path) -> None:
            self._tree = tree
            self.path = path
            super().__init__()

    KNOWN_COMMANDS = ["j", "k", "escape"]
    BINDINGS = [
        Binding("enter", "select_cursor", "Select"),
    ]

    can_focus = True
    command: str
    elems: list[ListItem]

    searchable: bool = True

    _tree: FilteredDirTree
    _cl: CommandLine

    _search_mode: bool
    _search_timer: Timer | None
    _before_search_index: int | None
    _is_filtered: bool

    def __init__(self, path, file_types: list[str] | None = None, **kwargs):
        super().__init__(path, **kwargs)
        self.path = path
        self.file_types = file_types
        self.command = ""
        self._search_mode = False
        self._search_timer = None
        self._before_search_index = None
        self._is_filtered = False

    @property
    def index(self):
        return self._tree.cursor_line

    @index.setter
    def index(self, value: int):
        self._tree.cursor_line = value

    @property
    def cursor_line(self):
        return self._tree.cursor_line

    @cursor_line.setter
    def set_cursor_line(self, value: int):
        self._tree.cursor_line = value

    def compose(self):
        self._tree = FilteredDirTree(self.path)
        yield self._tree
        self._cl = CommandLine()
        self._cl.display = False
        yield self._cl

    async def _run_search(self, query: str):
        self._tree.search_term = query
        await self._tree.reload()

    async def _reset_search(self):
        self._tree.search_term = ""
        await self._tree.reload()

    def focus(self):
        self._tree.focus()

    def move(self, steps: int, up: bool):
        pos = self._tree.cursor_line
        if up:
            steps = -steps
        self._tree.cursor_line = pos + steps
        return

    def action_select_cursor(self):
        node = self._tree.cursor_node
        if node.allow_expand:
            node.expand()
        else:
            msg = self.FileChosen(self._tree, node.data.path)
            self.post_message(msg)
        return


class MessageScreen(ModalScreen):
    BINDINGS = [
        Binding("q", "dismiss_modal", "Close", show=False),
        Binding("escape", "dismiss_modal", "Close"),
        Binding("enter", "dismiss_modal", "Close"),
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
        yield Footer()

    def action_dismiss_modal(self):
        self.dismiss(None)


class InputScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close"),
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
        yield Footer()

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
        Binding("escape", "dismiss_modal", "Close"),
        Binding("enter", "confirm", "Confirm"),
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
        yield Footer()

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


class FilePickerScreen(ModalScreen):
    BINDINGS = [
        ("n", "create_new_file", "New File"),
        ("escape", "quit", "Quit"),
    ]

    allow_file_creation: bool
    file_types: list[str] | None

    def __init__(self, allow_file_creation: bool = False, file_types: list[str] = None):
        super().__init__(classes="modal")
        self.selected_file = None
        self.allow_file_creation = allow_file_creation
        self.file_types = file_types
        self.initial_path = None  # Store path before search
        self._search_timer = None

    def compose(self):
        with Vertical(classes="modal-content"):
            yield Static("Select a file", classes="module-title")
            yield VimNavDirTree("~", id="file-tree", file_types=self.file_types)
        yield Footer()

    @on(VimNavDirTree.FileChosen)
    def on_file_chosen(self, event: VimNavDirTree.FileChosen) -> None:
        self.selected_file = event.path
        path = event.path
        self.log(f"Selected file: {path} ({type(path)})")
        self.dismiss(path)

    @work
    async def action_create_new_file(self):
        if not self.allow_file_creation:
            return
        """Create a new empty file in the current directory."""
        tree = self.query_one(VimNavDirTree)

        # Get the path at the current cursor location
        cursor_node = tree.cursor_node
        if cursor_node is None:
            current_dir = tree.path
        else:
            cursor_path = cursor_node.data.path
            # If cursor is on a file, use its parent directory
            current_dir = cursor_path if cursor_path.is_dir() else cursor_path.parent

        # Get filename from user
        filename = await self.app.push_screen_wait(InputScreen("Enter filename"))
        if filename is None or not filename.strip():
            return

        filename = filename.strip()
        new_file_path = Path(current_dir) / filename

        # Check if file already exists
        if new_file_path.exists():
            self.app.push_screen(
                MessageScreen(f"File already exists: {filename}", is_error=True)
            )
            return

        # Create the empty file
        try:
            new_file_path.touch()
            self.dismiss(new_file_path)
        except OSError as e:
            self.app.push_screen(
                MessageScreen(f"Could not create file: {str(e)}", is_error=True)
            )

    def action_quit(self):
        self.dismiss(None)
