from dataclasses import dataclass
from typing import Any, List, Dict, Optional
from pathlib import PurePath
import os

from mcsg.storage_backends.s3 import S3Storage
from mcsg.file_manager import FileManager
from mcsg.processor import Processor
from mcsg.commit_manager import CommitManager

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
    file_processors: Dict[str, Processor]
    threshold_size_mb: float

def create_commit_manager(config: Config) -> CommitManager:
    def _path_filter(rel_path: str, abs_path: str) -> bool:
        MB = 1024 * 1024
        return any(PurePath(rel_path).match(fstr) or os.path.getsize(abs_path) > config.threshold_size_mb * MB for fstr in config.include_files)

    def _path_processor_selector(path: str) -> Optional[Processor]:
        for fstr, processor in config.file_processors.items():
            if PurePath(path).match(fstr):
                return processor
        return None

    file_manager = FileManager(
        storage=S3Storage(config.storage_config),
        server_dir=config.server_dir,
        remote_root=config.remote_root,
        file_filter=_path_filter,
        file_processor_selector=_path_processor_selector,
    )

    return CommitManager(
        server_root=config.server_dir,
        file_manager=file_manager,
    )
