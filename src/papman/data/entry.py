from pathlib import Path
import subprocess
import re

from xml.etree import ElementTree as ET
import shutil
from uuid import UUID, uuid4
from collections.abc import Mapping
import bibtexparser
from bibtexparser.model import Entry as BibtexEntry
from bibtexparser.model import Field as BibtexField


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
            subprocess.Popen(
                ["xdg-open", str(self.path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True, ""
        except FileNotFoundError:
            return False, "xdg-open not found. Please install xdg-utils."
        except Exception as e:
            return False, f"Error opening file: {str(e)}"


class Entry:
    id: UUID
    key: str
    files: list[File]  # Can this be None or do I disallow this?
    doi: str | None
    title: str | None
    authors: list[str]
    date: str | None
    journal: str | None
    tags: list[str]
    notes: str | None

    def __init__(
        self,
        id: UUID,
        key: str,
        files,
        doi=None,
        title=None,
        date=None,
        authors=None,
        journal=None,
        tags=None,
        notes=None,
    ):
        self.id = id
        self.key = key
        self.files = files
        self.doi = doi
        self.title = title
        self.authors = authors if authors is not None else []
        self.date = date
        self.journal = journal
        self.tags = tags if tags is not None else []
        self.notes = notes

    def __repr__(self):
        return f"{self.title}"

    @property
    def author_str(self) -> str:
        if self.authors is None:
            return "No authors"
        return " AND ".join(self.authors)

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
        if file_element is not None:
            for child in file_element.findall("file"):
                file_id = UUID(child.get("id"))
                name = child.get("name")
                path = library_path / child.get("path")
                files.append(File(file_id, name, path))

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

        date_elem = root.find("date")
        date = date_elem.text if date_elem is not None else None
        journal_element = root.find("journal")
        journal = journal_element.text if journal_element is not None else None
        notes_element = root.find("notes")
        notes = notes_element.text if notes_element is not None else None
        tags_elem = root.find("tags")
        tags = [tag.text for tag in tags_elem.findall("tag")]

        return cls(
            id,
            key,
            files,
            doi=doi,
            title=title,
            authors=authors,
            date=date,
            journal=journal,
            tags=tags,
            notes=notes,
        )

    def save(self, library_path: Path):
        attrib = {"id": str(self.id), "key": self.key}
        root = ET.Element("entry", attrib=attrib)

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

        if self.date is not None:
            date_element = ET.SubElement(root, "date")
            date_element.text = self.date

        if self.notes is not None:
            notes_element = ET.SubElement(root, "notes")
            notes_element.text = self.notes

        files_elem = ET.SubElement(root, "files")
        for file in self.files:
            ET.SubElement(
                files_elem,
                "file",
                attrib={"id": str(file.id), "name": file.name, "path": file.path.name},
            )

        tag_elem = ET.SubElement(root, "tags")
        for tag in self.tags:
            t = ET.SubElement(tag_elem, "tag")
            t.text = tag

        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        tree.write(
            library_path / f"{self.id}.xml", encoding="utf-8", xml_declaration=True
        )

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

    @staticmethod
    def _clean_bibtex_text(value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if len(text) >= 2 and text[0] == "{" and text[-1] == "}":
            text = text[1:-1].strip()
        return text or None

    @classmethod
    def _extract_bibtex_fields(cls, bib_entry) -> dict[str, str]:
        fields: dict[str, str] = {}

        if isinstance(bib_entry, Mapping):
            for key, value in bib_entry.items():
                if key:
                    cleaned = cls._clean_bibtex_text(value)
                    if cleaned is not None:
                        fields[str(key).lower()] = cleaned
            return fields

        for field in getattr(bib_entry, "fields", []) or []:
            key = getattr(field, "key", None)
            value = getattr(field, "value", None)
            if key:
                cleaned = cls._clean_bibtex_text(value)
                if cleaned is not None:
                    fields[str(key).lower()] = cleaned
        return fields

    @staticmethod
    def _parse_bibtex_authors(raw_authors: str | None) -> list[str]:
        if not raw_authors:
            return []

        # BibTeX separates authors with the literal " and ".
        chunks = [c.strip() for c in re.split(r"\s+and\s+", raw_authors) if c.strip()]
        authors: list[str] = []
        for chunk in chunks:
            cleaned = chunk.strip("{} ")
            if "," in cleaned:
                authors.append(cleaned)
                continue

            parts = cleaned.split()
            if len(parts) <= 1:
                authors.append(cleaned)
            else:
                family = parts[-1]
                given = " ".join(parts[:-1])
                authors.append(f"{family}, {given}")
        return authors

    @classmethod
    def from_bibtex(
        cls,
        source: str,
        id: UUID | None = None,
        files: list[File] | None = None,
        doi: str | None = None,
        tags: list[str] | None = None,
        notes: str | None = None,
    ) -> "Entry":
        raw = (source or "").strip()
        if not raw:
            raise ValueError("BibTeX source cannot be empty.")

        try:
            library = bibtexparser.parse_string(raw)
            entries = list(getattr(library, "entries", []))
        except Exception as e:
            raise ValueError(f"Error parsing BibTeX: {str(e)}") from e

        if not entries:
            raise ValueError("Error: Parsed BibTeX contains no entries.")

        bib_entry = entries[0]
        entry_id = id or uuid4()
        fields = cls._extract_bibtex_fields(bib_entry)

        key = getattr(bib_entry, "key", None)
        if not key:
            raise ValueError("BibTeX entry must have a key.")
        title = fields.get("title")
        doi_value = doi or fields.get("doi")
        authors = cls._parse_bibtex_authors(fields.get("author"))

        date = fields.get("date")
        if date is None:
            year = fields.get("year")
            month = fields.get("month")
            if year and month:
                date = f"{year}-{month}"
            else:
                date = year

        journal = (
            fields.get("journal")
            or fields.get("journaltitle")
            or fields.get("booktitle")
            or fields.get("publisher")
        )

        if files is None:
            files = []

        return cls(
            entry_id,
            key,
            files,
            doi=doi_value,
            title=title,
            authors=authors,
            date=date,
            journal=journal,
            tags=tags,
            notes=notes,
        )

    def save_with_bibtex_source(self, library_path: Path, bibtex_source: str):
        bib_path = library_path / f"{self.id}.bib"
        bib_path.write_text((bibtex_source or "").strip() + "\n", encoding="utf-8")
        self.save(library_path)

    @staticmethod
    def _normalize_value(value: str | None) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _authors_to_bibtex(authors: list[str]) -> str | None:
        cleaned = [a.strip() for a in (authors or []) if str(a).strip()]
        if not cleaned:
            return None
        return " and ".join(cleaned)

    @staticmethod
    def _set_or_remove_bib_field(bib_entry: BibtexEntry, key: str, value: str | None):
        if value is None:
            bib_entry.pop(key, None)
            return
        bib_entry.set_field(BibtexField(key=key, value=value))

    @staticmethod
    def _date_parts(date_value: str | None) -> tuple[str | None, str | None]:
        if date_value is None:
            return None, None
        m = re.match(r"^\s*(\d{4})(?:-(\d{1,2}|[A-Za-z]{3,9}))?", date_value)
        if m is None:
            return None, None
        return m.group(1), m.group(2)

    def _update_bib_file(self, library_path: Path) -> tuple[bool, str]:
        bib_path = library_path / f"{self.id}.bib"
        try:
            if bib_path.exists():
                library = bibtexparser.parse_string(
                    bib_path.read_text(encoding="utf-8")
                )
            else:
                library = bibtexparser.Library()
        except Exception as e:
            return False, f"Error parsing BibTeX file '{bib_path.name}': {str(e)}"

        entries = list(getattr(library, "entries", []))
        if entries:
            bib_entry = entries[0]
        else:
            bib_entry = BibtexEntry(entry_type="misc", key=self.key, fields=[])
            library.add(bib_entry)

        bib_entry.key = self.key
        self._set_or_remove_bib_field(bib_entry, "doi", self._normalize_value(self.doi))
        self._set_or_remove_bib_field(
            bib_entry, "title", self._normalize_value(self.title)
        )
        self._set_or_remove_bib_field(
            bib_entry, "author", self._authors_to_bibtex(self.authors)
        )

        date_value = self._normalize_value(self.date)
        self._set_or_remove_bib_field(bib_entry, "date", date_value)
        year, month = self._date_parts(date_value)
        self._set_or_remove_bib_field(bib_entry, "year", year)
        self._set_or_remove_bib_field(bib_entry, "month", month)

        # Keep the canonical venue field aligned with entry metadata.
        self._set_or_remove_bib_field(
            bib_entry, "journal", self._normalize_value(self.journal)
        )

        try:
            bib_path.write_text(bibtexparser.write_string(library), encoding="utf-8")
        except Exception as e:
            return False, f"Error writing BibTeX file '{bib_path.name}': {str(e)}"
        return True, ""

    def update_from_dict(self, values: dict, library_path: Path) -> tuple[bool, str]:
        key = self._normalize_value(values.get("key"))
        if key is None:
            return False, "Citation key cannot be empty."

        title = self._normalize_value(values.get("title"))
        doi = self._normalize_value(values.get("doi"))
        date = self._normalize_value(values.get("date"))
        journal = self._normalize_value(values.get("journal"))

        authors_raw = values.get("authors") or []
        authors = [str(a).strip() for a in authors_raw if str(a).strip()]

        self.key = key
        self.title = title
        self.doi = doi
        self.date = date
        self.journal = journal
        self.authors = authors

        success, msg = self._update_bib_file(library_path)
        if not success:
            return False, msg

        self.save(library_path)
        return True, ""
