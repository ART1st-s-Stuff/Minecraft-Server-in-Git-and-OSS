from dataclasses import dataclass
from typing import Any, List
from pathlib import PurePath
import os

from mcsg.storage_backends.s3 import S3Storage
from mcsg.file_manager import FileManager

@dataclass
class Config:
    """Configuration class.

    Args:
        storage_config: Configuration for the storage backend.
        server_dir: The server directory.
        remote_root: The root directory on the remote storage.
        exclude_files: The list of regex patterns to exclude files.
    """
    storage_config: Any
    server_dir: str
    remote_root: str
    include_files: List[str]
    threshold_size_mb: float

def create_file_manager(config: Config) -> FileManager:
    def _regex_filter(rel_path: str, abs_path: str) -> bool:
        MB = 1024 * 1024
        return any(PurePath(rel_path).match(regex) or os.path.getsize(abs_path) > config.threshold_size_mb * MB for regex in config.include_files)

    return FileManager(
        storage=S3Storage(config.storage_config),
        server_dir=config.server_dir,
        remote_root=config.remote_root,
        file_filter=_regex_filter
    )