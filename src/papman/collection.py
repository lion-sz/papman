from textual import on, work
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Static, Input, Footer
from textual.containers import Vertical

from .shared import MessageScreen, ConfirmScreen

from .data.collection import Collection, Collections
from .paper import PaperList, FilePickerScreen


class CollectionSidebar(Static):
    collection = reactive(None)

    def __init__(self, collection: Collection):
        super().__init__(id="collection-sidebar", classes="sidebar")
        self.collection = collection

    def compose(self):
        if self.collection is None:
            yield Static("No Collection loaded")
        else:
            with Vertical():
                yield Static(self.collection.name)
                yield Static(f"{len(self.collection.papers)} papers loaded")


class CollectionPanel(Static):
    BINDINGS = [
        ("d", "remove_paper", "Remove"),
        ("b", "bibtex_export", "BibTeX Export"),
    ]
    paperlist: PaperList

    def compose(self) -> ComposeResult:
        lib = self.app.library
        if self.app.active_collection is None:
            yield Static("No Collection loaded")
        else:
            papers = []
            keys = []
            for paper_id, key in self.app.active_collection.papers.items():
                entry = lib.get_by_id(paper_id)
                assert entry is not None, f"Paper {paper_id} - {key} not found"
                papers.append(entry)
                keys.append(key)
            yield Static(f"Collection {self.app.active_collection.name}")
            self.paperlist = PaperList(papers, keys)
            yield self.paperlist

    def on_mount(self):
        self.query_one(PaperList).focus()

    @work
    async def action_remove_paper(self):
        self.app.push_screen(
            MessageScreen("Removing paper from collection...", is_error=False)
        )
        if self.app.collection is None:
            self.app.push_screen(MessageScreen("No collection loaded", is_error=True))
            return
        if self.paperlist.highlighted_child is None:
            self.app.push_screen(MessageScreen("No paper selected", is_error=True))
            return

        paper = self.paperlist.highlighted_child.paper
        key = self.app.collection.papers[paper.id][0]
        confirmed = await self.app.push_screen_wait(
            ConfirmScreen(f"Remove '{key}' from collection?")
        )
        if not confirmed:
            return

        success, msg = self.app.collection.remove(paper.id)
        if not success:
            self.app.push_screen(MessageScreen(msg, is_error=True))
            return

        self.app.query_one("#main-sidebar").reload_sidebar(
            section_to_focus="collection"
        )
        self.app.query_one("CollectionPanel").refresh(recompose=True)

    @work
    async def action_bibtex_export(self):
        if self.app.active_collection is None:
            self.app.push_screen(MessageScreen("No collection loaded", is_error=True))
            return

        screen = FilePickerScreen(allow_file_creation=True, file_types=[".bib"])
        export_path = await self.app.push_screen_wait(screen)
        if export_path is None:
            return

        lib = self.app.library
        bib_contents = []
        for paper_id in self.app.active_collection.papers:
            bib_source = lib.get_entry_bibtex_source(paper_id)
            if bib_source:
                bib_contents.append(bib_source.strip())

        try:
            export_path.write_text("\n\n".join(bib_contents), encoding="utf-8")
            self.app.push_screen(
                MessageScreen(
                    f"Exported {len(bib_contents)} entries to {export_path.name}",
                    is_error=False,
                )
            )
        except OSError as e:
            self.app.push_screen(MessageScreen(f"Export failed: {e}", is_error=True))


class NewCollectionScreen(ModalScreen):
    BINDINGS = [("escape", "on_escape", "Close")]

    def __init__(self, collections: Collections):
        super().__init__(classes="modal")
        self.collections = collections

    def compose(self):
        with Vertical(classes="modal-content"):
            yield Static("Creating a new Collection")
            yield Input(placeholder="Enter Collection Name", id="create_collection")
        yield Footer()

    @on(Input.Submitted, "#create_collection")
    def on_submit(self, event: Input.Submitted):
        name = self.query_one(Input).value
        collection = self.collections.create(name)
        self.dismiss(collection)

    def action_on_escape(self):
        self.app.pop_screen()
