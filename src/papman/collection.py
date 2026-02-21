from pathlib import Path
import os

from textual import on
from textual.app import ComposeResult
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Static, Input
from textual.containers import Vertical

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
    def compose(self) -> ComposeResult:
        if self.app.collection is None:
            yield Static("No Collection loaded")
        else:
            papers = [p[1] for i, p in self.app.collection.papers.items()]
            yield Static(f"Collection {self.app.collection.name}")
            yield PaperList(papers)


class NewCollectionScreen(ModalScreen):
    BINDINGS = [("escape", "on_escape", "Close")]

    def __init__(self):
        super().__init__(classes="modal")

    def compose(self):
        with Vertical(classes="modal-content"):
            yield Static("Creating a new Collection")
            yield Input(placeholder="Enter Collection Name", id="create_collection")

    @on(Input.Submitted, "#create_collection")
    def on_submit(self, event: Input.Submitted):
        path = Path(os.getcwd()) / "collection.xml"
        name = self.query_one(Input).value
        collection = Collection(path, name, {})
        collection.save()
        self.dismiss(collection)

    def action_on_escape(self):
        self.app.pop_screen()
