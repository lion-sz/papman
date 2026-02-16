from uuid import UUID
from pathlib import Path

import xml.etree.ElementTree as ET
from textual.screen import ModalScreen
from textual.containers import Vertical
from textual.widgets import Static, Input


from .entry import Entry


def load_collection(library_path: Path):
    """
    Check the current working directory for a 'collection.xml' file.
    If it exists, load it through the Collection class.
    
    Returns:
        Collection | None: The loaded Collection object if the file exists, None otherwise.
    """
    collection_path = Path.cwd() / "collection.xml"

    if collection_path.exists():
        return Collection.load(collection_path, library_path)

    return None


class Collection:

    path: Path
    name: str
    papers: dict[UUID, tuple[str, Entry]]

    def __init__(self, path: Path, name: str, papers: dict[UUID, tuple[str, Entry]]):
        self.path = path
        self.name = name
        self.papers = papers

    def save(self):
        root = ET.Element("collection", attrib={"name": self.name})

        for uuid, (key, entry) in self.papers.items():
            attrib = {
                "id": str(uuid),
                "key": key,
            }
            entry_element = ET.SubElement(root, "entry", attrib=attrib)

        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(self.path, encoding="utf-8", xml_declaration=True)

    @classmethod
    def load(cls, file: Path, library_path: Path):
        tree = ET.parse(file)
        root = tree.getroot()

        name = root.get("name")
        papers = {}

        for entry_element in root.findall("entry"):
            key = entry_element.get("key")
            entry_id = UUID(entry_element.get("id"))

            entry = Entry.load(library_path, entry_id)
            papers[entry_id] = (key, entry)

        return cls(Path(file), name, papers)

    def attach(self, paper: Entry, key: str) -> tuple[bool, str]:
        if key in self.papers:
            return False, f"Key '{key}' already exists."
        new_id = paper.id
        exists = False
        for i, _ in self.papers.values():
            if i == new_id:
                exists = True
                break
        if exists:
            return False, "Paper already attached."
        self.papers[paper.id] = (key, paper)
        self.save()
        return True, ""