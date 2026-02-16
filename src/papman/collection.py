from pathlib import Path
import os

from textual import on, work
from textual.app import App, ComposeResult, Binding
from textual.reactive import reactive
from textual.screen import ModalScreen, Screen
from textual.widgets import Footer, Header, Static, Input, Button, ListView, ListItem, Label, DirectoryTree
from textual.containers import Horizontal, Vertical, Grid

from .data.collection import load_collection, Collection
from .paper import PaperList


class CollectionSidebar(Static):

    collection = reactive(None)

    def __init__(self, collection: Collection, id: str, classes: str):
        super().__init__(id=id, classes=classes)
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
        ("n", "new", "New Collection"),
    ]

    def compose(self) -> ComposeResult:
        if self.app.collection is None:
            yield Static("No Collection loaded")
        else:
            papers = [p for i, p in self.app.collection.papers.items()]
            yield Static(self.app.collection.name)
            yield PaperList(papers)

    def action_new(self):
        pass


class NewCollectionScreen(ModalScreen):

    BINDINGS = [
        ("escape", "on_escape", "Close")
    ]

    def __init__(self):
        super().__init__(classes="modal")

    def compose(self):
        with Vertical(classes="modal-content"):
            yield Static("Creating a new Collection")
            yield Input(placeholder="Enter Collection Name")
            yield Button("Create", id="create-btn")

    @on(Button.Pressed, "#create-btn")
    def on_create_btn_pressed(self, event: Button.Pressed):
        path = Path(os.getcwd()) / "collection.xml"
        name = self.query_one(Input).value
        collection = Collection(path, name, {})
        collection.save()
        self.dismiss(collection)

    def action_on_escape(self):
        self.app.pop_screen()
