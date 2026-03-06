from textual import work, on
from textual.reactive import reactive
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static, Button, ListView, ListItem, Label
from textual.containers import Vertical

from .config import Config, load_config
from .paper import PapersModule, SearchScreen, PaperList
from .collection import CollectionPanel, NewCollectionScreen, CollectionSidebar
from .shared import MessageScreen, InputScreen, VimNavigableListView
from .data.library import Library
from .data.collection import Collection, load_collection


class MainModule(Static):
    content = reactive("paper", recompose=True)

    def compose(self):
        if self.content == "paper":
            yield PapersModule()
        elif self.content == "reading_list":
            yield ReadingListPanel()
        else:
            yield CollectionPanel()


class ReadingListSidebarItem(ListItem):
    def __init__(self, list_name: str, paper_count: int):
        super().__init__()
        self.list_name = list_name
        self.paper_count = paper_count

    def compose(self) -> ComposeResult:
        paper_label = "paper" if self.paper_count == 1 else "papers"
        yield Label(f"{self.list_name} ({self.paper_count} {paper_label})")


class ReadingListsList(VimNavigableListView):
    BINDINGS = [
        ("enter", "select_cursor", "Select"),
    ]


class ReadingListSidebar(Static):
    def __init__(self, library: Library):
        super().__init__(id="readinglist-sidebar", classes="sidebar")
        self.library = library

    def compose(self) -> ComposeResult:
        with Vertical(id="reading-lists-body"):
            yield Static("Reading Lists")
            if len(self.library.reading_lists.lists) == 0:
                yield Static("No reading lists found")
            else:
                items = [
                    ReadingListSidebarItem(reading_list.name, reading_list.paper_count)
                    for reading_list in sorted(
                        self.library.reading_lists.lists.values(),
                        key=lambda x: x.name.lower(),
                    )
                ]
                yield ReadingListsList(*items, id="reading-lists-list")
        yield Button(
            "New Reading List", id="new-reading-list", classes="sidebar-action"
        )

    @on(Button.Pressed, "#new-reading-list")
    @work
    async def on_new_reading_list_pressed(self):
        name = await self.app.push_screen_wait(
            InputScreen("Create reading list", "name")
        )
        if name is None:
            return
        success, msg = self.library.reading_lists.create(name)
        self.app.push_screen(MessageScreen(msg, is_error=not success))
        if success:
            self.refresh(recompose=True)

    @on(ListView.Selected, "#reading-lists-list")
    def on_reading_list_selected(self, event: ListView.Selected):
        item = event.item
        if item is None:
            return
        self.app.show_reading_list(item.list_name)


class ReadingListPanel(Static):
    def compose(self) -> ComposeResult:
        list_name = self.app.active_reading_list_name
        if not list_name:
            yield Static("No reading list selected")
            return
        reading_list = self.app.library.reading_lists.lists.get(list_name)
        if reading_list is None:
            yield Static(f"Reading list not found: {list_name}")
            return

        papers = []
        for paper_id in reading_list.paper_ids:
            entry = self.app.library.entries.get(paper_id)
            if entry is not None:
                papers.append(entry)

        with Vertical():
            yield Static(f"Reading List: {list_name}", classes="module-title")
            if len(papers) == 0:
                yield Static("No papers in this reading list")
            else:
                yield PaperList(papers)

    def on_mount(self):
        paper_lists = self.query(PaperList)
        for paper_list in paper_lists:
            paper_list.focus()
            break


class PapMan(App):
    CSS_PATH = "css/app.tcss"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("p", "papers", "Papers"),
        ("c", "collection", "Collection"),
        ("i", "import_entry", "Import"),
        ("n", "new_collection", "New Collection"),
        ("l", "focus_reading_lists", "Reading Lists"),
        ("/", "search", "Search"),
    ]

    collection: Collection
    library: Library
    config: Config
    active_reading_list_name: str | None

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.library = Library(self.config)
        self.collection = load_collection(self.library.path)
        self.active_reading_list_name = None

    def compose(self) -> ComposeResult:
        yield Header()

        yield CollectionSidebar(self.collection)
        yield MainModule(id="main")
        yield ReadingListSidebar(self.library)

        yield Footer()

    def action_quit(self):
        self.exit()

    def action_papers(self):
        self.query_one(MainModule).content = "paper"

    def action_collection(self):
        self.query_one(MainModule).content = "collection"

    def action_focus_reading_lists(self):
        sidebar = self.query_one(ReadingListSidebar)
        reading_lists = sidebar.query("#reading-lists-list")
        for reading_list_widget in reading_lists:
            if (
                reading_list_widget.index is None
                and len(reading_list_widget.children) > 0
            ):
                reading_list_widget.index = 0
            reading_list_widget.focus()
            break

    def show_reading_list(self, list_name: str):
        self.active_reading_list_name = list_name
        self.query_one(MainModule).content = "reading_list"

    def action_search(self):
        self.push_screen(SearchScreen())

    @work
    async def action_import_entry(self):
        doi = await self.push_screen_wait(InputScreen("Import by DOI", "DOI"))
        if doi is None:
            return

        msg = None
        if len(doi) < 5 or len(doi) > 40:
            msg = f"Doi length is not good: '{doi}'"
        elif "/" not in doi:
            msg = f"Doi does not contain a slash: '{doi}'"
        if msg is not None:
            await self.push_screen_wait(MessageScreen(msg, is_error=True))
            return
        success, res = self.app.library.load_entry_from_doi(doi)
        self.query_one(PapersModule).reload_papers()

    @work
    async def action_new_collection(self):
        if self.collection is not None:
            return None
        collection = await self.app.push_screen_wait(NewCollectionScreen())
        if collection is None:
            return
        msg = f"Created collection {collection.name}"
        self.push_screen(MessageScreen(msg))
        self.collection = collection
        self.query_one(CollectionSidebar).refresh()
        self.query_one(CollectionSidebar).refresh()
