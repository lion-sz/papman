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


class VimNavigableListView(Static):
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
        self.query_one(ListView).focus()

    @property
    def highlighted_child(self):
        return self.query_one(ListView).highlighted_child

    def compose(self):
        yield ListView(*self.elems, id=self.id, classes="box")
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
        list.clear()
        list.extend(filtered)
        list.focus()
        list.index = 0
        return

    def _reset_search(self):
        list = self.query_one(ListView)
        list.clear()
        list.extend(self.elems)
        list.focus()
        list.index = self._before_search_index

    async def _on_key(self, event: events.Key) -> None:
        cl = self.query_one(CommandLine)

        if event.key == "escape":
            event.stop()
            if self._is_filtered:
                self._search_mode = False
                self._is_filtered = False
                self._search_timer = None
                self._reset_search()
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
                    self.command = self.command[:-1] if self.command else self.command
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
        if self.searchable and event.key == "slash":
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


class FilteredDirectoryTree(DirectoryTree):
    file_types: list[str] | None
    search_term: str = ""

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

    def __init__(self, path: str, file_types: list[str] | None = None, **kwargs):
        super().__init__(path, **kwargs)
        self.file_types = file_types

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

    def action_select_cursor(self):
        node = self.cursor_node
        if node.allow_expand:
            node.expand()
        else:
            msg = self.FileChosen(self, node.data.path)
            self.post_message(msg)
        return

    def select_path(self, path: Path) -> None:
        """Select the node for the given path, or its nearest visible ancestor."""
        if not self.root:
            return

        target_path = path.expanduser().absolute()
        best_node = self.root

        # Helper to walk all loaded nodes
        def walk_tree(node):
            yield node
            for child in node.children:
                yield from walk_tree(child)

        # Walk all loaded nodes to find the best match
        for node in walk_tree(self.root):
            if node.data:
                try:
                    node_path = node.data.path.expanduser().absolute()
                    # If this node is the target or a parent of the target
                    if target_path == node_path or node_path in target_path.parents:
                        # We want the deepest match
                        if not best_node.data or len(node_path.parts) > len(
                            best_node.data.path.parts
                        ):
                            best_node = node
                except (ValueError, AttributeError):
                    continue

        self.move_cursor(best_node)
        self.scroll_to_node(best_node)


class FilePickerScreen(ModalScreen):
    BINDINGS = [
        ("enter", "select_file", "Select"),
        ("n", "create_new_file", "New File"),
        ("slash", "show_search", "Search"),
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
            yield FilteredDirectoryTree("~", id="file-tree", file_types=self.file_types)
            search_input = Input(
                placeholder="Search...", id="search-input", classes="search-bar"
            )
            search_input.display = False
            yield search_input
        yield Footer()

    @on(FilteredDirectoryTree.FileChosen)
    def on_file_chosen(self, event: FilteredDirectoryTree.FileChosen) -> None:
        self.selected_file = event.path
        path = event.path
        self.log(f"Selected file: {path} ({type(path)})")
        self.dismiss(path)

    @work
    async def action_create_new_file(self):
        if not self.allow_file_creation:
            return
        """Create a new empty file in the current directory."""
        tree = self.query_one("#file-tree", FilteredDirectoryTree)

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

    def action_show_search(self):
        tree = self.query_one("#file-tree", FilteredDirectoryTree)
        search_input = self.query_one("#search-input", Input)

        # Store current position if we're not already searching
        if not search_input.display and tree.cursor_node and tree.cursor_node.data:
            self.initial_path = tree.cursor_node.data.path

        search_input.display = True
        search_input.focus()

    @on(Input.Changed, "#search-input")
    def on_search_changed(self, event: Input.Changed):
        if self._search_timer is not None:
            self._search_timer.stop()
        self._search_timer = self.set_timer(0.2, lambda: self._run_search(event.value))

    @work(exclusive=True)
    async def _run_search(self, value: str):
        tree = self.query_one("#file-tree", FilteredDirectoryTree)
        tree.search_term = value
        tree.reload()

    @on(Input.Submitted, "#search-input")
    def on_search_submitted(self):
        tree = self.query_one("#file-tree", FilteredDirectoryTree)
        tree.focus()
        self.query_one("#search-input", Input).display = False
        if self.initial_path:
            tree.select_path(self.initial_path)

    def action_quit(self):
        search_input = self.query_one("#search-input", Input)
        if search_input.display:
            search_input.display = False
            search_input.value = ""
            tree = self.query_one("#file-tree", FilteredDirectoryTree)
            tree.search_term = ""
            tree.reload()
            tree.focus()
            if self.initial_path:
                self.call_after_refresh(tree.select_path, self.initial_path)
            return
        self.dismiss(None)
