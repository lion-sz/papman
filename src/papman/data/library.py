from uuid import UUID, uuid4
from pathlib import Path
import requests
import xml.etree.ElementTree as ET

from .entry import Entry
from .reading_list import ReadingLists
from papman.config import Config


class Library:
    path: Path
    entries: dict[UUID, Entry]
    reading_lists: ReadingLists

    def __init__(self, config: Config):
        self.path = config.library_path
        self.entries = {}

        if not (self.path / "library.xml").exists():
            self.populate()
        self.load_library()

    def load_library(self):
        """
        Loads the library.xml file and parses all entries into memory.
        """
        library_xml_path = self.path / "library.xml"
        assert library_xml_path.exists(), "Library XML file not found."

        try:
            tree = ET.parse(library_xml_path)
            root = tree.getroot()

            self.entries = {}
            for entry_element in root.findall("entry"):
                entry_id_raw = entry_element.get("id")
                if entry_id_raw:
                    entry_id = UUID(entry_id_raw)
                    entry = Entry.from_xml(self.path, entry_id, entry_element)
                    self.entries[entry_id] = entry
        except ET.ParseError as e:
            print(f"Error parsing library.xml: {e}")
        self.reading_lists = ReadingLists(self.path)

    def find_entry_by_id(self, entry_id: UUID) -> Entry | None:
        """
        Find an entry by its ID.

        Args:
            entry_id: The UUID of the entry

        Returns:
            The Entry object if found, None otherwise
        """
        return self.entries.get(entry_id)

    def find_entry_by_doi(self, doi: str) -> Entry | None:
        """
        Find an entry by its DOI.

        Args:
            doi: The DOI string of the entry

        Returns:
            The Entry object if found, None otherwise
        """
        for entry in self.entries.values():
            if entry.doi == doi:
                return entry
        return None

    def get_entry_bibtex_source(self, entry_id: UUID) -> str:
        bib_path = self.path / f"{entry_id}.bib"
        if not bib_path.exists():
            return ""
        try:
            return bib_path.read_text(encoding="utf-8")
        except OSError:
            return ""

    def update_entry_from_bibtex(
        self, entry_id: UUID, bibtex_source: str
    ) -> tuple[bool, str]:
        entry = self.find_entry_by_id(entry_id)
        if entry is None:
            return False, f"Entry not found: {entry_id}"

        try:
            candidate = Entry.from_bibtex(
                bibtex_source,
                id=entry.id,
                files=entry.files,
                tags=entry.tags,
            )
        except ValueError as e:
            return False, str(e)

        if candidate.doi:
            existing = self.find_entry_by_doi(candidate.doi)
            if existing is not None and existing.id != entry.id:
                return (
                    False,
                    f"DOI already exists on a different entry: {candidate.doi}",
                )
        try:
            candidate.save_with_bibtex_source(self.path, bibtex_source)
        except OSError as e:
            return False, f"Error saving entry '{entry_id}': {str(e)}"

        self.entries[entry_id] = candidate
        self.populate()
        return True, "Entry updated."

    def populate(self):
        """
        Collects all XML files from the library folder and merges them into a single library.xml file.
        """
        # Create root element for the library XML
        library_root = ET.Element("library")

        # Find all XML files in the library path
        xml_files = list(self.path.glob("*.xml"))

        # Parse each XML file and add its content to the library root
        for xml_file in xml_files:
            if xml_file.name in {"library.xml", ReadingLists.FILE_NAME}:
                continue
            try:
                tree = ET.parse(xml_file)
                entry_root = tree.getroot()
                # Append the entry element to the library root
                library_root.append(entry_root)
            except ET.ParseError as e:
                print(f"Error parsing {xml_file}: {e}")
                continue

        # Create the library XML tree and write to file
        library_tree = ET.ElementTree(library_root)
        library_xml_path = self.path / "library.xml"

        # Write with pretty formatting
        ET.indent(library_tree, space="  ")
        library_tree.write(library_xml_path, encoding="utf-8", xml_declaration=True)

        return library_xml_path

    def load_entry_from_doi(self, doi: str) -> tuple[bool, str]:
        # First check that this entry does not yet exist.
        if self.find_entry_by_doi(doi) is not None:
            return True, "Entry already exists."

        url = f"https://doi.org/{doi}"
        headers = {"Accept": "application/x-bibtex"}

        try:
            response = requests.get(url, headers=headers, timeout=20)
        except requests.RequestException as e:
            return False, f"Error: Request failed: {str(e)}"

        if response.status_code != 200:
            return (
                False,
                f"Error: Request failed with status code {response.status_code}",
            )

        bibtex_raw = response.text.strip()
        if not bibtex_raw:
            return False, "Error: Empty BibTeX response from DOI endpoint."

        id = uuid4()
        try:
            entry = Entry.from_bibtex(bibtex_raw, id=id, files=[], doi=doi)
            entry.save_with_bibtex_source(self.path, bibtex_raw)
        except ValueError as e:
            return False, str(e)
        except OSError as e:
            return False, f"Error saving entry '{id}': {str(e)}"

        self.entries[id] = entry
        self.populate()
        return True, f"Entry saved with ID: {id}"
