from pathlib import Path
import os

from textual import on, work
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Static, Input, Footer
from textual.containers import Vertical

from .shared import MessageScreen, ConfirmScreen

from .data.collection import Collection
from .paper import PaperList


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
    ]
    paperlist: PaperList

    def compose(self) -> ComposeResult:
        if self.app.collection is None:
            yield Static("No Collection loaded")
        else:
            papers = [p[1] for i, p in self.app.collection.papers.items()]
            keys = [p[0] for i, p in self.app.collection.papers.items()]
            yield Static(f"Collection {self.app.collection.name}")
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


class NewCollectionScreen(ModalScreen):
    BINDINGS = [("escape", "on_escape", "Close")]

    def __init__(self):
        super().__init__(classes="modal")

    def compose(self):
        with Vertical(classes="modal-content"):
            yield Static("Creating a new Collection")
            yield Input(placeholder="Enter Collection Name", id="create_collection")
        yield Footer()

    @on(Input.Submitted, "#create_collection")
    def on_submit(self, event: Input.Submitted):
        path = Path(os.getcwd()) / "collection.xml"
        name = self.query_one(Input).value
        collection = Collection(path, name, {})
        collection.save()
        self.dismiss(collection)

    def action_on_escape(self):
        self.app.pop_screen()
