from textual import work, on
from textual.reactive import reactive
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static, Tree
from .config import Config, load_config
from .paper import PapersModule, PaperList
from .collection import CollectionPanel, NewCollectionScreen
from .shared import MessageScreen, InputScreen, VimNavTree
from .data.library import Library
from .data.collection import Collection, Collections
from .data.reading_list import ReadingLists


class PapMan(App):
    CSS_PATH = "css/app.tcss"
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("n", "navigation", "Toggle Nav"),
        ("i", "import_entry", "Import"),
        ("p", "focus_paper", "Focus Paper"),
    ]

    config: Config
    library: Library
    collections: Collections
    reading_lists: ReadingLists

    active_collection: Collection | None
    active_reading_list_name: str | None

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.library = Library(self.config)
        self.collections = Collections(self.library)
        self.reading_lists = ReadingLists(self.config.library_path)
        self.active_collection = None
        self.active_reading_list_name = None

    def compose(self) -> ComposeResult:
        yield Header()

        yield MainSidebar()
        yield MainModule(id="main")

        yield Footer()

    def action_quit(self):
        self.exit()

    def action_navigation(self):
        sidebar_tree = self.query_one(SidebarTree)
        if sidebar_tree.has_focus_within:
            self._focus_main_panel()
            return
        sidebar_tree.focus()

    def action_focus_paper(self):
        self.query_one(MainModule).content = "paper"
        self._focus_main_panel()

    def _focus_main_panel(self):
        self.query_one(MainModule).focus()

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


class MainModule(Static):
    content = reactive("paper", recompose=True)

    def compose(self):
        if self.content == "paper":
            yield PapersModule()
        elif self.content == "reading_list":
            yield ReadingListPanel()
        else:
            yield CollectionPanel()

    def focus(self):
        if self.content == "paper":
            self.query_one(PaperList).focus()
        elif self.content == "reading_list":
            self.query_one(ReadingListPanel).focus()
        else:
            self.query_one(CollectionPanel).focus()


class SidebarTree(VimNavTree):
    label: str
    collections: dict[str, Collection]
    reading_lists: list[str]
    tags: list[str]

    def __init__(
        self,
        label: str,
        collections: dict[str, Collection],
        reading_lists: list[str],
        tags: list[str],
        **kwargs,
    ):
        super().__init__(label, **kwargs)
        self.label = label
        self.collections = collections
        self.reading_lists = reading_lists
        self.tags = tags

    def build_tree(self):
        tree = Tree(self.label)
        tree.root.expand()
        tree.show_root = False
        coll_elem = tree.root.add("collections", expand=True)
        for name, coll in self.collections.items():
            coll_elem.add_leaf(
                f"{name} ({len(coll.papers)} papers)", data=("coll", name)
            )
        coll_elem.add_leaf("new collection", data=("new_coll", "new_collection"))

        readings_elem = tree.root.add("reading_lists", expand=False)
        for name, reading_list in self.reading_lists.items():
            readings_elem.add_leaf(
                f"{name} ({len(reading_list.paper_ids)} papers)", data=("rl", name)
            )
        readings_elem.add_leaf("new reading list", data=("new_rl", "new_reading_list"))

        tags_elem = tree.root.add("tags", expand=False)
        for tag in self.tags:
            tags_elem.add(tag, data=("tags", tag))

        return tree

    @on(Tree.NodeSelected)
    def on_selected(self, event: Tree.NodeSelected):
        node = event.node
        if node.data is None:
            return
        node_type, payload = node.data
        if node_type == "coll":
            # Collection
            if (
                self.app.active_collection is None
                or self.app.active_collection.name != payload
            ):
                self.app.active_collection = self.app.collections.get(payload)
            self.app.query_one(MainModule).content = "collection"

        elif node_type == "new_coll":
            self.create_new_collection()
        elif node_type == "rl":
            self.app.active_reading_list_name = payload
            self.app.query_one(MainModule).content = "reading_list"
        elif node_type == "new_rl":
            self.create_reading_list()
        else:
            raise ValueError(f"Unknown node type: {node_type}")

    @work
    async def create_new_collection(self):
        collection = await self.app.push_screen_wait(
            NewCollectionScreen(self.app.collections)
        )
        if collection is None:
            return
        msg = f"Created collection {collection.name}"
        self.app.push_screen(MessageScreen(msg))
        self.app.active_collection = collection
        self.app.query_one(MainSidebar).recompose()

    @work
    async def create_reading_list(self):
        name = await self.app.push_screen_wait(
            InputScreen("Create reading list", "name")
        )
        if name is None:
            return
        success, msg = self.app.reading_lists.create(name)
        self.app.push_screen(MessageScreen(msg, is_error=not success))
        if success:
            self.app.query_one(MainSidebar).recompose()


class MainSidebar(Static):
    def __init__(self):
        super().__init__(id="main-sidebar", classes="sidebar")

    def compose(self) -> ComposeResult:
        yield SidebarTree(
            label="Navigation",
            collections=self.app.collections.collections,
            reading_lists=self.app.reading_lists.lists,
            tags=[],
        )


class ReadingListPanel(Static):
    def compose(self) -> ComposeResult:
        list_name = self.app.active_reading_list_name
        if not list_name:
            yield Static("No reading list selected")
            return
        reading_list = self.app.reading_lists.lists.get(list_name)
        if reading_list is None:
            yield Static(f"Reading list not found: {list_name}")
            return

        papers = []
        for paper_id in reading_list.paper_ids:
            entry = self.app.library.entries.get(paper_id)
            if entry is not None:
                papers.append(entry)

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
