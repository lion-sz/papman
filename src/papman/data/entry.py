from pathlib import Path
import subprocess

from xml.etree import ElementTree as ET
import shutil
from uuid import UUID, uuid4
from citeproc import Citation



class File:
    id: UUID
    name: str
    path: Path

    def __init__(self, id: UUID, name: str, path: Path):
        self.id = id
        self.name = name
        self.path = path

    def __repr__(self):
        return f"File(name='{self.name}', path='{self.path}')"

    def open(self) -> tuple[bool, str]:
        """
        Opens the file with the default application in a new process.
        
        Returns:
            tuple[bool, str]: (success, error_message)
        """
        if not self.path.exists():
            return False, f"File not found: {self.path}"

        try:
            subprocess.Popen(['xdg-open', str(self.path)],
                             stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return True, ""
        except FileNotFoundError:
            return False, "xdg-open not found. Please install xdg-utils."
        except Exception as e:
            return False, f"Error opening file: {str(e)}"

class Entry:
    id: UUID
    key: str
    files: list[File]  # Can this be None or do I disallow this?
    data: Citation | None
    doi: str | None
    title: str | None
    authors: list[str]
    journal: str | None

    def __init__(
        self,
        id: UUID,
        key: str,
        files,
        citation=None,
        doi=None,
        title=None,
        authors=None,
        journal=None,
    ):
        self.id = id
        self.key = key
        self.files = files
        self.citation = citation
        self.doi = doi
        self.title = title
        self.authors = authors if authors is not None else []
        self.journal = journal

    def __repr__(self):
        return f"{self.title}"

    @classmethod
    def load(cls, library_path: Path, id: UUID) -> "Entry":
        tree = ET.parse(library_path / f"{id}.xml")
        root = tree.getroot()
        return cls.from_xml(library_path, id, root)

    @classmethod
    def from_xml(cls, library_path: Path, id: UUID, root: ET.Element) -> "Entry":

        key = root.get("key")

        files = []
        file_element = root.find("files")
        for child in file_element.findall("file"):
            id = UUID(child.get("id"))
            name = child.get("name")
            path = library_path / child.get("path")
            files.append(File(id, name, path))

        doi_element = root.find("doi")
        doi = doi_element.text if doi_element is not None else None

        title_element = root.find("title")
        title = title_element.text if title_element is not None else None

        authors = []
        authors_element = root.find("authors")
        if authors_element is not None:
            for author_element in authors_element.findall("author"):
                if author_element.text is not None:
                    authors.append(author_element.text)

        journal_element = root.find("journal")
        journal = journal_element.text if journal_element is not None else None

        return cls(id, key, files, doi=doi, title=title, authors=authors, journal=journal)

    def save(self, library_path: Path):
        root = ET.Element("entry", attrib={"id": str(self.id), "key": self.key})

        if self.doi is not None:
            doi_element = ET.SubElement(root, "doi")
            doi_element.text = self.doi

        if self.title is not None:
            title_element = ET.SubElement(root, "title")
            title_element.text = self.title

        authors_element = ET.SubElement(root, "authors")
        for author in self.authors:
            author_element = ET.SubElement(authors_element, "author")
            author_element.text = author

        if self.journal is not None:
            journal_element = ET.SubElement(root, "journal")
            journal_element.text = self.journal

        files_elem = ET.SubElement(root, "files")
        for file in self.files:
            ET.SubElement(
                files_elem, "file",
                attrib={"id": str(file.id), "name": file.name, "path": file.path.name},
            )

        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(library_path / f"{self.id}.xml", encoding="utf-8", xml_declaration=True)

    def attach(self, file_path: Path, library_path: Path) -> tuple[bool, str]:
        """
        Attach a file to this entry by copying it to the library path.

        Args:
            file_path: Path to the file to attach
            library_path: Path to the library directory where the file will be copied
        """
        file_path = Path(file_path)
        if not file_path.exists():
            return False, f"File not found: {file_path}"

        # Create destination path with UUID as filename, preserving extension
        file_id = uuid4()
        file_extension = file_path.suffix
        file_name = file_path.name
        dest_filename = f"{file_id}{file_extension}"
        dest_path = library_path / dest_filename
        shutil.copy2(file_path, dest_path)

        # Create File object and append to files
        new_file = File(file_id, file_name, dest_path)
        self.files.append(new_file)

        # Save the entry with updated files
        self.save(library_path)
        return True, ""

    @classmethod
    def from_citation(cls, id: UUID, citation: Citation, files=None, doi=None):
        key = citation.key
        if "title" in citation:
            title = str(citation.title)
        else:
            title = ""
        authors = []
        if "author" in citation:
            for a in citation.author:
                authors.append(f"{a["family"]}, {a["given"]}")

        if "journal" in citation:
            journal = str(citation.journal)
        elif "publisher" in citation:
            journal = str(citation.publisher)
        else:
            journal = ""

        if files is None:
            files = []

        return cls(id, key, files, citation=citation, doi=doi, title=title, authors=authors, journal=journal)
