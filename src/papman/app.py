from textual import on, work
from textual.reactive import reactive
from textual.app import App, ComposeResult, Binding
from textual.screen import ModalScreen, Screen
from textual.widgets import Footer, Header, Static, Input, Button, ListView, ListItem, Label, DirectoryTree
from textual.containers import Horizontal, Vertical, Grid

from .config import Config, load_config
from .paper import PapersModule, ImportScreen
from .collection import CollectionPanel, NewCollectionScreen, CollectionSidebar
from .shared import MessageScreen, InputScreen
from .data.library import Library
from .data.collection import Collection, load_collection


class MainModule(Static):

    content = reactive("paper", recompose=True)

    def compose(self):
        if self.content == "paper":
            yield PapersModule()
        else:
            yield CollectionPanel()


class PapMan(App):
    CSS_PATH = "css/app.tcss"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("p", "papers", "Papers"),
        ("c", "collection", "Collection"),
        ("i", "import_entry", "Import"),
        ("n", "new_collection", "New Collection"),
    ]

    collection: Collection
    library: Library
    config: Config

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.library = Library(self.config)
        self.collection = load_collection(self.library.path)

    def compose(self) -> ComposeResult:
        yield Header()

        yield Static("Library", id="library", classes="sidebar")
        yield MainModule()
        yield CollectionSidebar(self.collection, id="collection", classes="sidebar")

        yield Footer()

    def action_quit(self):
        self.exit()

    def action_papers(self):
        self.query_one(MainModule).content = "paper"

    def action_collection(self):
        self.query_one(MainModule).content = "collection"

    @work
    async def action_import_entry(self):
        doi = await self.push_screen_wait(InputScreen("Import by DOI", "DOI"))

        msg = None
        if len(doi) < 5 or len(doi) > 20:
            msg = f"Doi length is not good: '{doi}'"
        elif "/" not in doi:
            msg = f"Doi does not contain a slash: '{doi}'"
        if msg is not None:
            await self.push_screen_wait(MessageScreen(msg, is_error=True))
            return
        success, res = self.app.library.load_entry_from_doi(doi)
        self.app.push_screen(MessageScreen(res, is_error=False))

    @work
    async def action_new_collection(self):
        collection = await self.app.push_screen_wait(NewCollectionScreen())
        self.push_screen(MessageScreen(collection.name))
        self.query_one(CollectionSidebar).collection = "collection"