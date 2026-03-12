from textual import work, on
from textual.reactive import reactive
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Static, ListView, ListItem, Label
from .config import Config, load_config
from .paper import PapersModule, PaperList
from .collection import CollectionPanel, NewCollectionScreen
from .shared import MessageScreen, InputScreen, VimNavigableListView
from .data.library import Library
from .data.collection import Collection, Collections


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
    active_collection: Collection | None
    active_reading_list_name: str | None

    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.library = Library(self.config)
        self.collections = Collections(self.library)
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
        sidebar_list = self.query_one("#sidebar-list", SidebarList)
        if sidebar_list.has_focus:
            self._focus_main_panel()
            return
        if sidebar_list.index is None and len(sidebar_list.children) > 0:
            sidebar_list.index = 0
        sidebar_list.focus()

    def action_focus_paper(self):
        self.query_one(MainModule).content = "paper"
        self._focus_main_panel()

    def _focus_main_panel(self):
        for paper_list in self.query(PaperList):
            paper_list.focus()
            return
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


class SidebarRowItem(ListItem):
    def __init__(
        self,
        label: str,
        row_kind: str,
        section: str | None = None,
        payload: str | None = None,
    ):
        super().__init__()
        self.label = label
        self.row_kind = row_kind
        self.section = section
        self.payload = payload

    def compose(self) -> ComposeResult:
        yield Label(self.label)


class SidebarList(VimNavigableListView):
    BINDINGS = [
        ("enter", "select_cursor", "Select"),
    ]


class MainSidebar(Static):
    def __init__(self):
        super().__init__(id="main-sidebar", classes="sidebar")
        self._expanded_sections = {
            "collection": False,
            "reading_lists": False,
            "tags": False,
        }

    def compose(self) -> ComposeResult:
        yield SidebarList(*self._build_rows(), id="sidebar-list")

    def _build_rows(self) -> list[SidebarRowItem]:
        rows: list[SidebarRowItem] = []
        rows.append(
            SidebarRowItem(
                self._section_label("collection"),
                row_kind="section",
                section="collection",
            )
        )
        if self._expanded_sections["collection"]:
            for name, collection in self.app.collections.collections.items():
                n_paper = len(collection.papers)
                rows.append(
                    SidebarRowItem(
                        f"  {name} ({n_paper})",
                        payload=name,
                        row_kind="collection",
                        section=collection,
                    )
                )
            rows.append(
                SidebarRowItem(
                    "  + new collection",
                    row_kind="new_collection",
                    section="collection",
                )
            )

        rows.append(
            SidebarRowItem(
                self._section_label("reading_lists"),
                row_kind="section",
                section="reading_lists",
            )
        )
        if self._expanded_sections["reading_lists"]:
            reading_lists = sorted(
                self.app.library.reading_lists.lists.values(),
                key=lambda x: x.name.lower(),
            )
            if len(reading_lists) == 0:
                rows.append(SidebarRowItem("  no reading lists", "meta"))
            else:
                for reading_list in reading_lists:
                    paper_label = "paper" if reading_list.paper_count == 1 else "papers"
                    rows.append(
                        SidebarRowItem(
                            f"  {reading_list.name} ({reading_list.paper_count} {paper_label})",
                            row_kind="reading_list",
                            section="reading_lists",
                            payload=reading_list.name,
                        )
                    )
            rows.append(
                SidebarRowItem(
                    "  + new reading list",
                    row_kind="new_reading_list",
                    section="reading_lists",
                )
            )

        rows.append(
            SidebarRowItem(
                self._section_label("tags"),
                row_kind="section",
                section="tags",
            )
        )
        if self._expanded_sections["tags"]:
            tag_counts: dict[str, int] = {}
            for paper in self.app.library.entries.values():
                for tag in getattr(paper, "tags", []):
                    normalized = tag.strip()
                    if normalized:
                        tag_counts[normalized] = tag_counts.get(normalized, 0) + 1
            tags = sorted(tag_counts.items(), key=lambda x: x[0].lower())
            if len(tags) == 0:
                rows.append(SidebarRowItem("  no tags", "meta"))
            else:
                for tag, count in tags:
                    paper_label = "paper" if count == 1 else "papers"
                    rows.append(
                        SidebarRowItem(
                            f"  {tag} ({count} {paper_label})",
                            row_kind="tag",
                            section="tags",
                            payload=tag,
                        )
                    )
        return rows

    def _section_label(self, section: str) -> str:
        marker = "▾" if self._expanded_sections[section] else "▸"
        title = section.replace("_", " ")
        return f"{marker} {title}"

    def focus_section(self, section: str):
        sidebar_list = self.query_one(SidebarList)
        target_index = None
        for idx, child in enumerate(sidebar_list.children):
            if (
                isinstance(child, SidebarRowItem)
                and child.row_kind == "section"
                and child.section == section
            ):
                target_index = idx
                break
        if target_index is None:
            target_index = 0
        if len(sidebar_list.children) > 0:
            sidebar_list.index = target_index
            sidebar_list.focus()

    @work(exclusive=True)
    async def reload_sidebar(self, section_to_focus: str | None = None):
        sidebar_list = self.query_one(SidebarList)
        list_view = sidebar_list.query_one(ListView)
        had_focus = list_view.has_focus
        old_index = sidebar_list.index
        rows = self._build_rows()

        sidebar_list.elems = rows
        list_view.clear()
        list_view.extend(rows)

        if len(rows) > 0:
            if section_to_focus is None:
                sidebar_list.index = (
                    0 if old_index is None else min(old_index, len(rows) - 1)
                )
            else:
                sidebar_list.index = 0
                for idx, child in enumerate(rows):
                    if (
                        isinstance(child, SidebarRowItem)
                        and child.row_kind == "section"
                        and child.section == section_to_focus
                    ):
                        sidebar_list.index = idx
                        break
        if had_focus:
            sidebar_list.focus()

    @on(ListView.Selected, "#sidebar-list")
    def on_sidebar_selected(self, event: ListView.Selected):
        item = event.item
        if item is None or not isinstance(item, SidebarRowItem):
            return
        if item.row_kind == "section" and item.section is not None:
            self._expanded_sections[item.section] = not self._expanded_sections[
                item.section
            ]
            self.reload_sidebar(section_to_focus=item.section)
        elif item.row_kind == "collection":
            if (
                self.app.active_collection is None
                or self.app.active_collection.name != item.payload
            ):
                self.app.active_collection = self.app.collections.get(item.payload)
            self.app.query_one(MainModule).content = "collection"
        elif item.row_kind == "new_collection":
            self.create_new_collection()
        elif item.row_kind == "reading_list" and item.payload is not None:
            self.app.active_reading_list_name = item.payload
            self.app.query_one(MainModule).content = "reading_list"
        elif item.row_kind == "new_reading_list":
            self.create_reading_list()

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
        self.reload_sidebar(section_to_focus="collection")

    @work
    async def create_reading_list(self):
        name = await self.app.push_screen_wait(
            InputScreen("Create reading list", "name")
        )
        if name is None:
            return
        success, msg = self.app.library.reading_lists.create(name)
        self.app.push_screen(MessageScreen(msg, is_error=not success))
        if success:
            self.reload_sidebar(section_to_focus="reading_lists")


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
