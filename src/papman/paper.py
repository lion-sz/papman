from textual import on, work
from textual.app import App, ComposeResult, Binding
from textual.screen import ModalScreen, Screen
from textual.widgets import Footer, Header, Static, Input, Button, ListView, ListItem, Label, DirectoryTree
from textual.containers import Horizontal, Vertical, Grid

from .shared import MessageScreen


class PapersModule(Static):

    def compose(self) -> ComposeResult:
        papers = list(self.app.library.entries.values())
        with Vertical():
            yield Static("Papers", classes="module-title")
            yield PaperList(papers)

    def on_mount(self):
        self.query_one(PaperList).focus()


class PaperList(ListView):
    BINDINGS = [
        Binding("enter", "select_cursor", "Select"),
        Binding("r", "refresh", "Refresh Library"),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("a", "attach", "Attach Paper"),
        Binding("o", "open", "Open"),
    ]

    def __init__(self, papers):
        papers = [PaperListItem(paper) for paper in papers]
        super().__init__(*papers)

    def action_select_cursor(self):
        paper = self.highlighted_child.paper
        self.app.push_screen(PaperModal(paper))

    def action_refresh(self):
        self.app.library.populate()

    @work
    async def action_attach(self):
        key = await self.app.push_screen_wait(AttachPaperScreen())
        if key is None:
            return
        paper = self.highlighted_child.paper
        success, msg = self.app.collection.attach(paper, key)
        if not success:
            self.app.push_screen(MessageScreen(msg))

    def action_open(self):
        paper = self.highlighted_child.paper
        if len(paper.files) > 0:
            success, msg = paper.files[0].open()
            if not success:
                self.app.push_screen(MessageScreen(msg))

class ImportScreen(ModalScreen):
    CSS_PATH = "css/import_screen.tcss"
    BINDINGS = [
        ("escape", "app.pop_screen", "Exit"),
    ]

    def __init__(self):
        super().__init__(classes="modal")

    def compose(self):
        with Vertical(id="import-screen", classes="modal-content"):
            yield Static("Importing by DOI")
            yield Input(placeholder="Enter DOI", id="doi-input")

    @on(Input.Submitted, "#doi-input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        doi = event.value
        msg = None
        if len(doi) < 5 or len(doi) > 20:
            msg = f"Doi length is not good: '{doi}'"
        elif "/" not in doi:
            msg = f"Doi does not contain a slash: '{doi}'"
        if msg is not None:
            self.app.push_screen(MessageScreen(msg, is_error=True))
            return
        success, res = self.app.library.load_entry_from_doi(event.value)
        self.app.push_screen(MessageScreen(res, is_error=False))


class FilePickerScreen(ModalScreen):
    BINDINGS = [
        ("escape", "app.pop_screen", "Cancel"),
        ("enter", "select_file", "Select"),
    ]

    def __init__(self):
        super().__init__(classes="modal")
        self.selected_file = None

    def compose(self):
        with Vertical(classes="modal-content"):
            yield Static("Select a file", classes="module-title")
            yield DirectoryTree("~", id="file-tree")
            with Horizontal():
                yield Button("Cancel", id="cancel-btn")
                yield Button("Select", id="select-btn")

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel_pressed(self) -> None:
        self.app.pop_screen()

    @on(Button.Pressed, "#select-btn")
    def on_select_pressed(self) -> None:
        tree = self.query_one("#file-tree", DirectoryTree)
        if tree.cursor_node:
            path = tree.cursor_node.data.path
            self.dismiss(str(path))


class PaperModal(ModalScreen):
    CSS_PATH = "css/paper_modal.tcss"
    BINDINGS = [
        ("escape", "on_escape", "Close"),
        ("a", "attach", "Attach File"),
        ("c", "collect", "Add to Collection"),
    ]

    def __init__(self, paper):
        self.paper = paper
        super().__init__(classes="modal")

    def compose(self):
        authors = "and ".join(self.paper.authors)
        with Vertical(id="paper-modal", classes="modal-content"):
            yield Label(self.paper.title, id="title")
            yield Label(authors)
            yield Label(self.paper.journal)

            if len(self.paper.files) > 0:
                yield Static("Files:")
                for f in self.paper.files:
                    yield Static(f.name)

    def action_on_escape(self) -> None:
        self.app.pop_screen()

    @work
    async def action_attach(self):
        path = await self.app.push_screen_wait(FilePickerScreen())
        success, msg = self.paper.attach(path, self.app.library.path)
        if not success:
            self.app.push_screen(MessageScreen(msg))


class PaperListItem(ListItem):

    def __init__(self, paper):
        self.paper = paper
        super().__init__(Label(str(paper), classes="paper-item"))


class AttachPaperScreen(ModalScreen):

    BINDINGS = [
        ("escape", "on_escape", "Close")
    ]

    def __init__(self):
        super().__init__(classes="modal")

    def compose(self):
        with Vertical(classes="modal-content"):
            yield Static("Attach Paper to Collection")
            yield Input(placeholder="Citation Key")
            yield Button("Attach", id="attach-btn")

    @on(Button.Pressed, "#attach-btn")
    def action_attach(self, event: Button.Pressed):
        key = self.query_one(Input).value
        self.dismiss(key)

    def action_on_escape(self) -> None:
        self.dismiss(None)
