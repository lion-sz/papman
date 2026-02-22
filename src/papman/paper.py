from textual import on, work
from textual.app import ComposeResult, Binding
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import (
    Static,
    Input,
    Button,
    ListView,
    ListItem,
    Label,
    TextArea,
)
from textual.containers import Horizontal, Vertical

from .shared import MessageScreen, FilteredDirectoryTree
from .data.entry import Entry


# --- new: two-line paper widget ---------------------------------------------------
class PaperTwoLine(ListItem):
    def __init__(self, paper):
        super().__init__(classes="paper-two-line")
        self.paper = paper

    def compose(self) -> ComposeResult:
        title = (self.paper.title or "").strip() or "<untitled>"
        authors = (
            ", ".join(self.paper.authors)
            if getattr(self.paper, "authors", None)
            else ""
        )
        date = self.paper.date
        journal = (getattr(self.paper, "journal", None) or "").strip()

        with Static(classes="paper-item-elem"):
            yield Label(title, classes="paper-elem paper-title")
            yield Label(authors, classes="paper-elem paper-author")
            yield Label(date, classes="paper-elem")
            yield Label(journal, classes="paper-elem")


class PapersModule(Static):
    def compose(self) -> ComposeResult:
        papers = list(self.app.library.entries.values())
        with Vertical():
            yield Static("Papers", classes="module-title")
            yield PaperList(papers)

    def on_mount(self):
        self.query_one(PaperList).focus()

    @work(exclusive=True)
    async def reload_papers(self):
        papers = list(self.app.library.entries.values())
        new_list = PaperList(papers)
        old_list = self.query_one(PaperList)
        had_focus = old_list.has_focus
        old_index = old_list.index

        await old_list.remove()
        await self.query_one(Vertical).mount(new_list)

        if old_index is not None and len(new_list.children) > 0:
            new_list.index = min(old_index, len(new_list.children) - 1)
        if had_focus:
            new_list.focus()


class PaperList(ListView):
    BINDINGS = [
        Binding("enter", "select_cursor", "Select"),
        Binding("r", "refresh", "Refresh Library"),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("a", "attach", "Attach Paper"),
        Binding("o", "open", "Open"),
        Binding("e", "edit", "Edit Metadata"),
    ]

    def __init__(self, papers, id=None):
        papers = [PaperTwoLine(paper) for paper in papers]
        super().__init__(*papers, id=id)

    def action_select_cursor(self):
        paper = self.highlighted_child.paper
        if paper is None:
            raise ValueError("No paper selected")
        self.app.push_screen(PaperModal(paper))

    def action_refresh(self):
        self.app.library.populate()

    @work
    async def action_attach(self):
        paper = self.highlighted_child.paper
        if paper.id in self.app.collection.papers:
            self.app.push_screen(MessageScreen("Paper already attached", is_error=True))
            return
        key = await self.app.push_screen_wait(AttachPaperScreen(paper))
        if key is None:
            return
        if self.app.collection is None:
            self.app.push_screen(MessageScreen("No collection loaded", is_error=True))
            return
        success, msg = self.app.collection.attach(paper, key)
        if not success:
            self.app.push_screen(MessageScreen(msg))
        else:
            self.app.query_one("#collection-sidebar").refresh()

    def action_open(self):
        paper = self.highlighted_child.paper
        if len(paper.files) > 0:
            success, msg = paper.files[0].open()
            if not success:
                self.app.push_screen(MessageScreen(msg))

    @work
    async def action_edit(self):
        paper = self.highlighted_child.paper
        bib_source = self.app.library.get_entry_bibtex_source(paper.id)
        draft = await self.app.push_screen_wait(EntryEditScreen(bib_source))
        if draft is not None:
            success, msg = self.app.library.update_entry_from_bibtex(paper.id, draft)
            self.app.push_screen(MessageScreen(msg, is_error=not success))
            if success:
                self.app.query_one(PapersModule).reload_papers()


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
            yield FilteredDirectoryTree("~", id="file-tree")

    @on(FilteredDirectoryTree.FileChosen)
    def on_file_chosen(self, event: FilteredDirectoryTree.FileChosen) -> None:
        self.selected_file = event.path
        path = event.path
        self.log(f"Selected file: {path} ({type(path)})")
        self.dismiss(path)


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
        journal = self.paper.journal
        if journal is None:
            journal = "Journal not found"
        with Vertical(id="paper-modal", classes="modal-content"):
            yield Label(self.paper.title, id="title")
            yield Label(self.paper.author_str)
            yield Label(journal)

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


class AttachPaperScreen(ModalScreen):
    BINDINGS = [("escape", "on_escape", "Close")]

    def __init__(self, paper: Entry):
        self.paper = paper
        super().__init__(classes="modal")

    def compose(self):
        with Vertical(classes="modal-content"):
            yield Static("Attach Paper to Collection")
            yield Input(placeholder=self.paper.key, id="attach-input")

    @on(Input.Submitted, "#attach-input")
    def action_attach(self, event: Input.Submitted):
        key = self.query_one(Input).value
        self.dismiss(key)

    def action_on_escape(self) -> None:
        self.dismiss(None)


class EntryEditScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("ctrl+s", "save", "Done"),
    ]

    def __init__(self, bibtex_source: str):
        super().__init__(classes="modal")
        self.bibtex_source = bibtex_source

    def compose(self):
        with Vertical(classes="modal-content entry-edit-screen"):
            yield Static("Edit BibTeX Source", classes="module-title")
            yield TextArea(self.bibtex_source, id="entry-edit-bibtex")
            with Horizontal(classes="entry-edit-actions"):
                yield Button("Cancel", id="entry-edit-cancel")
                yield Button("Save", id="entry-edit-done", variant="primary")

    def _collect_draft(self) -> str:
        return self.query_one("#entry-edit-bibtex", TextArea).text

    def action_cancel(self):
        self.dismiss(None)

    def action_save(self):
        self.dismiss(self._collect_draft())

    @on(Button.Pressed, "#entry-edit-cancel")
    def on_cancel_pressed(self):
        self.dismiss(None)

    @on(Button.Pressed, "#entry-edit-done")
    def on_done_pressed(self):
        self.dismiss(self._collect_draft())


class SearchScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "close", "Close"),
    ]

    def __init__(self):
        super().__init__(classes="modal")
        self._search_timer: Timer | None = None

    def compose(self):
        with Vertical(id="search-modal", classes="modal-content"):
            yield PaperList([], id="search-results")
            yield Input(placeholder="Type to search...", id="search-query")

    def on_mount(self):
        self.query_one("#search-query", Input).focus()

    def action_close(self):
        self.dismiss(None)

    @on(Input.Changed, "#search-query")
    def on_search_input_changed(self, event: Input.Changed):
        if self._search_timer is not None:
            self._search_timer.stop()
        self._search_timer = self.set_timer(0.2, lambda: self._run_search(event.value))

    @on(Input.Submitted, "#search-query")
    def on_search_input_submitted(self, _: Input.Submitted):
        results = self.query_one("#search-results", PaperList)
        if len(results.children) == 0:
            return
        if results.index is None:
            results.index = 0
        results.focus()

    @work(exclusive=True)
    async def _run_search(self, query: str):
        # Placeholder for future, real search backend integration.
        papers = self._search_papers(query)
        results = self.query_one("#search-results", PaperList)
        had_focus = results.has_focus
        old_index = results.index
        results.clear()
        for paper in papers:
            results.append(PaperTwoLine(paper))

        if old_index is not None and len(results.children) > 0:
            results.index = min(old_index, len(results.children) - 1)
        if had_focus:
            results.focus()

    def _search_papers(self, query: str):
        papers = list(self.app.library.entries.values())
        q = query.strip().lower()
        if not q:
            return papers

        def matches(paper):
            haystack = [
                paper.title or "",
                paper.author_str,
            ]
            text = " ".join(haystack).lower()
            return q in text

        return [paper for paper in papers if matches(paper)]
