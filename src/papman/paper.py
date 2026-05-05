import subprocess
from pathlib import Path
from tempfile import NamedTemporaryFile

from textual import on, work
from textual.app import ComposeResult, Binding
from textual.screen import ModalScreen
from textual.widgets import (
    Static,
    Input,
    Button,
    Footer,
    ListView,
    ListItem,
    Label,
    TextArea,
    Markdown,
)
from textual.containers import Horizontal, Vertical

from .shared import MessageScreen, FilePickerScreen, InputScreen
from .shared import VimNavList
from .data.entry import Entry
from .data.library import search_papers


class PaperListItem(ListItem):
    def __init__(self, paper, key=None):
        super().__init__(classes="paper-item")
        self.paper = paper
        self.key = key

    def compose(self) -> ComposeResult:
        key = self.key if self.key is not None else self.paper.key
        title = (self.paper.title or "").strip() or "<untitled>"
        authors = (
            ", ".join(self.paper.authors)
            if getattr(self.paper, "authors", None)
            else ""
        )
        date = self.paper.date
        journal = (getattr(self.paper, "journal", None) or "").strip()
        tags_str = ", ".join(self.paper.tags)

        with Static(classes="paper-item-grid"):
            yield Label(key, classes="paper-item-label paper-key")
            yield Label(title, classes="paper-item-label paper-title")
            yield Label(authors, classes="paper-item-label paper-author")
            yield Label(date, classes="paper-item-label")
            yield Label(journal, classes="paper-item-label")
            yield Label("", classes="paper-item-label")
            yield Label(tags_str, classes="paper-item-label paper-tags")


class PaperList(VimNavList):
    BINDINGS = [
        Binding("a", "attach", "Attach Paper"),
        Binding("c", "create", "Create Entry"),
        Binding("o", "open", "Open"),
        Binding("e", "edit", "Edit Metadata"),
    ]
    papers: list[Entry]
    searchable: bool = True

    def __init__(self, papers: list[Entry], keys: list[str] = None, id=None):
        self.papers = papers
        items = []
        for i, p in enumerate(papers):
            if keys is not None:
                items.append(PaperListItem(p, keys[i]))
            else:
                items.append(PaperListItem(p))
        super().__init__(*items, id=id)

    def run_search(self, query: str) -> list[PaperListItem]:
        filtered = search_papers(self.papers, query)
        elements = [PaperListItem(p) for p in filtered]
        return elements

    def _get_selected_paper(self) -> Entry | None:
        item = self.highlighted_child
        if item is None:
            return None
        return item.paper

    @on(ListView.Selected)
    def paper_details(self, event: ListView.Selected) -> None:
        paper = self._get_selected_paper()
        if paper is None:
            return
        self.app.push_screen(PaperModal(paper))

    @work
    async def action_attach(self):
        paper = self._get_selected_paper()
        if paper is None:
            return
        if self.app.active_collection is None:
            self.app.push_screen(MessageScreen("No collection loaded", is_error=True))
            return
        if paper.id in self.app.active_collection.papers:
            self.app.push_screen(MessageScreen("Paper already attached", is_error=True))
            return
        key = await self.app.push_screen_wait(AttachPaperScreen(paper))
        if key is None:
            return
        success, msg = self.app.active_collection.attach(paper, key)
        self.app.collections.save()
        if not success:
            self.app.push_screen(MessageScreen(msg))
        else:
            await self.app.query_one("#main-sidebar").reload_sidebar(
                section_to_focus="collection"
            )

    @work
    async def action_create(self):
        draft = await self.app.push_screen_wait(EntryEditScreen(""))
        if draft is None:
            return
        success, msg = self.app.library.load_entry_from_bibtex(draft)
        self.app.push_screen(MessageScreen(msg, is_error=not success))
        if success:
            self.app.query_one(PapersModule).reload_papers()

    def action_open(self):
        paper = self._get_selected_paper()
        if paper is None:
            return
        if len(paper.files) > 0:
            success, msg = paper.files[0].open()
            if not success:
                self.app.push_screen(MessageScreen(msg))

    @work
    async def action_edit(self):
        paper = self._get_selected_paper()
        if paper is None:
            return
        bib_source = self.app.library.get_entry_bibtex_source(paper.id)
        draft = await self.app.push_screen_wait(EntryEditScreen(bib_source))
        if draft is not None:
            success, msg = self.app.library.update_entry_from_bibtex(paper.id, draft)
            self.app.push_screen(MessageScreen(msg, is_error=not success))
            if success:
                self.recompose()


class PapersModule(Static):
    def compose(self) -> ComposeResult:
        papers = list(self.app.library.entries.values())
        yield PaperList(papers, id="paper_list")

    def on_mount(self):
        self.query_one("#paper_list").focus()

    @work(exclusive=True)
    async def reload_papers(self):
        papers = list(self.app.library.entries.values())
        new_list = PaperList(papers)
        old_list = self.query_one(PaperList)
        had_focus = old_list.has_focus or old_list.query_one(ListView).has_focus
        old_index = old_list.index

        await old_list.remove()
        await self.mount(new_list)

        if old_index is not None and len(papers) > 0:
            new_list.index = min(old_index, len(papers) - 1)
        if had_focus:
            new_list.focus()


class PaperModal(ModalScreen):
    CSS_PATH = "css/paper_modal.tcss"
    BINDINGS = [
        ("escape", "on_escape", "Close"),
        ("a", "attach", "Attach File"),
        ("c", "collect", "Add to Collection"),
        ("l", "add_to_reading_list", "Add to Reading List"),
        ("t", "add_tag", "Edit Tags"),
        ("n", "edit_notes", "Edit Notes"),
    ]

    def __init__(self, paper):
        self.paper = paper
        super().__init__(classes="modal")

    def compose(self):
        title = (self.paper.title or "").strip() or "<untitled>"
        authors = (getattr(self.paper, "author_str", None) or "").strip()
        if not authors:
            authors = "Unknown authors"
        journal = (self.paper.journal or "").strip() if self.paper.journal else ""
        if not journal:
            journal = "Journal not found"
        date = (getattr(self.paper, "date", None) or "").strip() or "Date unknown"

        with Vertical(id="paper-modal", classes="modal-content"):
            with Vertical(id="paper-header"):
                yield Static(self.paper.key, id="paper-key")
                yield Label(title, id="title")
                yield Label(authors, id="paper-authors")
                yield Label(f"{date}  |  {journal}", id="paper-meta")

            with Vertical(classes="paper-section"):
                yield Static("Tags", classes="paper-section-title")
                yield Label(self._tags_text(), id="paper-tags")

            if len(self.paper.files) > 0:
                with Vertical(classes="paper-section"):
                    yield Static("Files", classes="paper-section-title")
                    for f in self.paper.files:
                        yield Static(f.name, classes="paper-file")

            with Vertical(classes="paper-section", id="paper-notes-section"):
                yield Static("Notes", classes="paper-section-title")
                yield Markdown(self._notes_markdown(), id="paper-notes")
        yield Footer()

    def action_on_escape(self) -> None:
        self.app.pop_screen()

    @work
    async def action_attach(self):
        path = await self.app.push_screen_wait(FilePickerScreen(file_types=[".pdf"]))
        if path is None:
            return
        success, msg = self.paper.attach(path, self.app.library.path)
        if not success:
            self.app.push_screen(MessageScreen(msg))
            return
        self.app.library.save_library()

    @work
    async def action_add_tag(self):
        new_tag = await self.app.push_screen_wait(InputScreen("Add tag to paper"))
        if new_tag is None:
            return

        new_tag = new_tag.strip()
        if new_tag in self.paper.tags:
            return
        self.paper.tags.append(new_tag)
        self.paper.save(self.app.library.path)
        self.app.library.populate()
        for item in self.app.query(PaperList):
            item.refresh()

    @work
    async def action_add_to_reading_list(self):
        reading_lists = self.app.reading_lists
        if len(reading_lists.lists) == 0:
            self.app.push_screen(
                MessageScreen("No reading lists available. Create one in the sidebar.")
            )
            return

        selected_list = await self.app.push_screen_wait(
            SelectReadingListScreen(reading_lists)
        )
        if selected_list is None:
            return

        success, msg = reading_lists.add_paper(selected_list, self.paper.id)
        self.app.push_screen(MessageScreen(msg, is_error=not success))
        if success:
            await self.app.query_one("#main-sidebar").reload_sidebar(
                section_to_focus="reading_lists"
            )

    def action_edit_notes(self):
        temp_path: Path | None = None
        old_notes = self.paper.notes or ""
        try:
            with NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=".md",
                prefix="papman-notes-",
                dir="/tmp",
                delete=False,
            ) as temp_file:
                temp_file.write(old_notes)
                temp_path = Path(temp_file.name)

            with self.app.suspend():
                return_code = subprocess.call(["nvim", str(temp_path)])

            if return_code != 0:
                self.app.push_screen(
                    MessageScreen("nvim exited with non-zero status", is_error=True)
                )
                return

            new_notes = temp_path.read_text(encoding="utf-8")
            self.paper.notes = new_notes
            self.paper.save(self.app.library.path)
            self.app.library.populate()
            self._refresh_notes_view()
        except FileNotFoundError:
            self.app.push_screen(MessageScreen("nvim not found", is_error=True))
        except OSError as e:
            self.app.push_screen(
                MessageScreen(f"Could not edit notes: {str(e)}", is_error=True)
            )
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _tags_text(self) -> str:
        if not getattr(self.paper, "tags", None):
            return "none"
        return ", ".join(self.paper.tags)

    def _notes_markdown(self) -> str:
        notes = self.paper.notes or ""
        if notes.strip():
            return notes
        return "_No notes yet. Press `n` to edit._"

    def _refresh_notes_view(self) -> None:
        notes_view = self.query_one("#paper-notes", Markdown)
        notes_view.update(self._notes_markdown())


class AttachPaperScreen(ModalScreen):
    BINDINGS = [("escape", "on_escape", "Close")]

    def __init__(self, paper: Entry):
        self.paper = paper
        super().__init__(classes="modal")

    def compose(self):
        with Vertical(classes="modal-content"):
            yield Static("Attach Paper to Collection")
            yield Input(placeholder=self.paper.key, id="attach-input")
        yield Footer()

    @on(Input.Submitted, "#attach-input")
    def submit_result(self, event: Input.Submitted):
        key = self.query_one(Input).value
        if key is None or len(key) == 0:
            key = self.paper.key
        self.dismiss(key)

    def action_on_escape(self) -> None:
        self.dismiss(None)


class ReadingListItem(ListItem):
    def __init__(self, list_name: str, paper_count: int):
        super().__init__()
        self.list_name = list_name
        self.paper_count = paper_count

    def compose(self):
        paper_label = "paper" if self.paper_count == 1 else "papers"
        yield Label(f"{self.list_name} ({self.paper_count} {paper_label})")


class SelectReadingListScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("enter", "select", "Select"),
    ]

    def __init__(self, reading_lists):
        super().__init__(classes="modal")
        self.reading_lists = reading_lists

    def compose(self):
        with Vertical(classes="modal-content"):
            yield Static("Add paper to reading list", classes="module-title")
            items = [
                ReadingListItem(reading_list.name, reading_list.paper_count)
                for reading_list in sorted(
                    self.reading_lists.lists.values(),
                    key=lambda x: x.name.lower(),
                )
            ]
            yield VimNavList(*items, id="reading-list-picker")
        yield Footer()

    def on_mount(self):
        self.query_one("#reading-list-picker", VimNavList).focus()

    def action_cancel(self):
        self.dismiss(None)

    def action_select(self):
        picker = self.query_one("#reading-list-picker", VimNavList)
        if picker.highlighted_child is None:
            self.dismiss(None)
            return
        self.dismiss(picker.highlighted_child.list_name)

    @on(ListView.Selected, "#reading-list-picker")
    def on_pick_reading_list(self, event: ListView.Selected):
        item = event.item
        if item is None:
            self.dismiss(None)
            return
        self.dismiss(item.list_name)


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
        yield Footer()

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
