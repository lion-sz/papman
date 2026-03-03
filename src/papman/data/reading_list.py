from pathlib import Path
from uuid import UUID
from xml.etree import ElementTree as ET


class ReadingList:
    name: str
    paper_ids: list[UUID]

    def __init__(self, name: str, paper_ids: list[UUID]):
        self.name = name
        self.paper_ids = paper_ids

    @property
    def paper_count(self) -> int:
        return len(self.paper_ids)


class ReadingLists:
    FILE_NAME = "reading_lists.xml"

    path: Path
    lists: dict[str, ReadingList]

    def __init__(self, library_path: Path):
        self.path = library_path / self.FILE_NAME
        self.lists = {}
        if not self.path.exists():
            self.save()
        self.load()

    def load(self) -> None:
        self.lists = {}
        tree = ET.parse(self.path)
        root = tree.getroot()

        for list_element in root.findall("reading-list"):
            name = list_element.get("name")
            if not name:
                continue
            paper_ids: list[UUID] = []
            for paper_element in list_element.findall("paper"):
                paper_id_raw = paper_element.get("id")
                if not paper_id_raw:
                    continue
                paper_ids.append(UUID(paper_id_raw))
            self.lists[name] = ReadingList(name=name, paper_ids=paper_ids)

    def save(self) -> None:
        root = ET.Element("reading-lists")
        for reading_list in sorted(self.lists.values(), key=lambda x: x.name.lower()):
            list_element = ET.SubElement(
                root, "reading-list", {"name": reading_list.name}
            )
            for paper_id in reading_list.paper_ids:
                ET.SubElement(list_element, "paper", {"id": str(paper_id)})

        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(self.path, encoding="utf-8", xml_declaration=True)

    def create(self, name: str) -> tuple[bool, str]:
        normalized = name.strip()
        if not normalized:
            return False, "Reading list name cannot be empty."
        if normalized in self.lists:
            return False, f"Reading list already exists: {normalized}"
        self.lists[normalized] = ReadingList(name=normalized, paper_ids=[])
        self.save()
        return True, f"Created reading list: {normalized}"

    def add_paper(self, list_name: str, paper_id: UUID) -> tuple[bool, str]:
        if list_name not in self.lists:
            return False, f"Reading list not found: {list_name}"
        reading_list = self.lists[list_name]
        if paper_id in reading_list.paper_ids:
            return False, f"Paper already in reading list: {list_name}"
        reading_list.paper_ids.append(paper_id)
        self.save()
        return True, f"Added paper to reading list: {list_name}"
