from typing import NamedTuple
import os
from pathlib import Path
import tomllib


class Config(NamedTuple):
    library_path: Path


def load_config(config_path: str | Path | None = None) -> Config:
    """
    Load PapMan config from TOML.

    Resolution order:
      1) explicit config_path argument
      2) environment variable PAPMAN_CONFIG
      3) ./papman.toml (current working directory)
      4) ~/.config/papman/config.toml

    Returns a Config namedtuple that always contains:
      library_path: string path to the library
    """
    candidates: list[Path] = []

    if config_path is not None:
        candidates.append(Path(config_path))

    env_path = os.environ.get("PAPMAN_CONFIG")
    if env_path:
        candidates.append(Path(env_path))

    candidates.append(Path("~/.config/papman/config.toml").expanduser())

    chosen: Path | None = next((p for p in candidates if p.exists()), None)

    data: dict = {}
    if chosen is not None:
        raw = chosen.read_bytes()
        data = tomllib.loads(raw.decode("utf-8"))

    library = data.get("library", {})
    assert "path" in library, "Library path not specified in config"
    library_path = library["path"]

    # Normalize to a string path (expanded). Keep it simple and predictable.
    normalized = Path(library_path).expanduser()

    return Config(normalized)
