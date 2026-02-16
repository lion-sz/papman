import json
import uuid
from pathlib import Path
import requests
import xml.etree.ElementTree as ET

from citeproc.source.json import CiteProcJSON

from .entry import Entry
from papman.config import Config


class Library:

    path: Path

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

            for entry_element in root.findall("entry"):
                entry_id = entry_element.get("id")
                if entry_id:
                    entry = Entry.from_xml(self.path, uuid.UUID(entry_id), entry_element)
                    self.entries[entry_id] = entry
        except ET.ParseError as e:
            print(f"Error parsing library.xml: {e}")

    def find_entry_by_id(self, entry_id: str) -> Entry | None:
        """
        Find an entry by its ID.
        
        Args:
            entry_id: The UUID string of the entry
            
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
            if xml_file.name == "library.xml":
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
        headers = {"Accept": "application/vnd.citationstyles.csl+json"}

        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            return False, f"Error: Request failed with status code {response.status_code}"

        content_type = response.headers.get("Content-Type", "")
        if "application/vnd.citationstyles.csl+json" not in content_type:
            return False, f"Error: Expected JSON content type, but got {content_type}"

        data = json.loads(response.text)
        try:
            data["id"] = doi
            citation = CiteProcJSON([data])
            citation = citation[doi]
        except Exception as e:
            return False, f"Error parsing JSON: {str(e)}"
        id = uuid.uuid4()
        entry = Entry.from_citation(id, citation, files=[], doi=doi)
        entry.save(self.path)
        with open(self.path / f"{id}.json", "w") as f:
            f.write(json.dumps(data, indent=2))
        self.populate()
        return True, f"Entry saved with ID: {id}"
