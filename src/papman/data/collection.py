from pathlib import Path
import atexit
from uuid import UUID

import xml.etree.ElementTree as ET

from .entry import Entry
from .library import Library


class Collections:
    FILE_NAME = "collection.xml"

    path: Path
    library: Library
    collections: dict[str, "Collection"]

    def __init__(self, library: Library):
        self.library = library
        self.path = library.path / self.FILE_NAME
        self.collections = self._load_all()
        atexit.register(self.save)

    def _load_all(self) -> dict[str, "Collection"]:
        if not self.path.exists():
            return {}

        tree = ET.parse(self.path)
        root = tree.getroot()
        result = {}

        if root.tag != "collections":
            raise ValueError("Invalid collections file format.")

        for collection_element in root.findall("collection"):
            loaded = Collection.load_xml(collection_element)
            if loaded is not None:
                result[loaded.name] = loaded
            else:
                raise ValueError("Invalid collection format.")
        return result

    def save(self):
        tree = ET.ElementTree(ET.Element("collections"))
        root = tree.getroot()
        for collection in self.collections.values():
            root.append(collection._to_xml_element())
        tree.write(self.path, encoding="utf-8", xml_declaration=True)

    def get(self, name: str) -> "Collection | None":
        return self.collections.get(name)

    def create(self, name: str) -> "Collection":
        collection = Collection(name, {})
        self.collections[name] = collection
        return collection


class Collection:
    name: str
    papers: dict[UUID, str]

    def __init__(self, name: str, papers: dict[UUID, str]):
        self.name = name
        self.papers = papers

    def _to_xml_element(self) -> ET.Element:
        root = ET.Element("collection", attrib={"name": self.name})
        for uuid, key in self.papers.items():
            ET.SubElement(root, "entry", attrib={"id": str(uuid), "key": key})
        return root

    @classmethod
    def load_xml(cls, element: ET.Element):
        name = element.get("name")
        papers = {}

        for entry_element in element.findall("entry"):
            key = entry_element.get("key")
            entry_id = UUID(entry_element.get("id"))
            papers[entry_id] = key

        return cls(name, papers)

    def attach(self, paper: Entry, key: str) -> tuple[bool, str]:
        if paper.id in self.papers:
            return False, f"Paper '{key}' already attached."
        if key in self.papers.values():
            return False, "Key already in use."
        self.papers[paper.id] = key
        return True, ""

    def remove(self, paper_id: UUID) -> tuple[bool, str]:
        if paper_id not in self.papers:
            return False, "Paper is not in the collection."
        del self.papers[paper_id]
        return True, ""

    def export(self, library: Library, output_path: Path) -> tuple[bool, str]:
        parts = []
        for paper_id in self.papers:
            bib = library.get_entry_bibtex_source(paper_id)
            if bib:
                parts.append(bib)
        try:
            output_path.write_text("\n".join(parts), encoding="utf-8")
        except OSError as e:
            return False, f"Error writing export file: {str(e)}"
        return True, ""
