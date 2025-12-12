from dataclasses import dataclass
from typing import Tuple, List, Callable, Optional, Dict
import os
import json
import hashlib
import logging

from mcsg.storage import RemoteStorage
from mcsg.git import Git
from mcsg.processor import Processor

try:
    from tqdm import tqdm
except ImportError:
    tqdm = lambda x: x
    logging.warning("tqdm is not installed, progress bar will not be displayed")

class FileHashMismatchException(Exception):
    def __init__(self, path: str):
        self.path = path

    def __str__(self):
        return f"Hash mismatch for file {self.path}"

@dataclass
class FileMeta:
    remote_path: str
    hash: str
    updated_at: float
    processor: Optional[str]

    @classmethod
    def from_meta(cls, meta_path: str) -> "FileMeta":
        with open(meta_path, "r", encoding="utf-8") as f:
            return cls(**json.load(f))

    @classmethod
    def from_file(cls, remote_path: str, file_path: str, processor: Optional[str] = None) -> "FileMeta":
        with open(file_path, "rb") as f:
            return cls(remote_path=remote_path, hash=hashlib.sha256(f.read()).hexdigest(), updated_at=os.path.getmtime(file_path), processor=processor)
    
    def to_meta(self, meta_path: str):
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(self.__dict__, f)

    def validate(self, file_path: str, strict: bool = False) -> bool:
        if not os.path.exists(file_path):
            return False
        
        if not strict and os.path.getmtime(file_path) == self.updated_at:
            return True
        
        with open(file_path, "rb") as f:
            return self.hash == hashlib.sha256(f.read()).hexdigest()

@dataclass
class FileManager:
    """Main class for managing blobs on the server with help of git.

    Args:
        storage: The storage backend to use.
        server_dir: The server directory.
        remote_root: The root directory on the remote storage.
        file_filter: Selects which files to track.
    """
    storage: RemoteStorage
    server_dir: str
    remote_root: str
    file_filter: Callable[[str, str], bool]     # Input 1: relative path, Input 2: absolute path
    file_processor_selector: Callable[[str], Processor]  # Input: absolute path, Output: processor

    def _get_hash(self, path: str) -> str:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def _get_rel_path(self, path: str) -> str:
        return os.path.relpath(path, self.server_dir)

    def _get_abs_path(self, rel_path: str) -> str:
        return os.path.join(self.server_dir, rel_path)

    def _get_abs_meta_path(self, rel_path: str) -> str:
        return self._get_abs_path(os.path.join("meta", rel_path + ".meta"))
    
    def _get_abs_tmp_path(self, rel_path: str) -> str:
        return self._get_abs_path(os.path.join("tmp", rel_path))

    def get_remote_path(self, prefix: str, rel_path: str) -> str:
        return self.storage.join_path(self.remote_root, prefix, rel_path)

    def pull_file(self, path: str, strict: bool = False) -> Tuple[Optional[Callable[[], None]], Optional[Callable[[], None]]]:
        """Pull from remote storage to local server directory.

        Args:
            path: The path to the file.
            strict: If set to False, will not compare hash if modified time is the same.

        Returns:
            callback_success: Callback to replace the local file with the temporary file on success case.
            callback_fail: Callback to delete the temporary file on failing case.
        """
        rel_path = self._get_rel_path(path)
        meta_path = self._get_abs_meta_path(rel_path)
        tmp_path = self._get_abs_tmp_path(rel_path)
        if not os.path.exists(meta_path):
            return None, None

        meta = FileMeta.from_meta(meta_path)
        if meta.validate(path, strict):
            return None, None
        
        logging.info("Pulling file %s", path)
        self.storage.retrieve(
            local_path_list=[tmp_path],
            remote_path_list=[meta.remote_path]
        )

        processor = self.file_processor_selector(path)
        if processor is not None:
            processor.unprocess(tmp_path, path)

        if self._get_hash(tmp_path) != meta.hash:
            raise FileHashMismatchException(path)

        return lambda: os.replace(tmp_path, path), lambda: os.remove(tmp_path)

    def push_file(self, prefix: str, path: str, git: Git, strict: bool = False) -> Tuple[Optional[Callable[[], None]], Optional[Callable[[], None]], Optional[str]]:
        """Push the file to the remote storage and update the meta file.

        Args:
            prefix: The prefix for the remote path.
            path: The path to the file.
            git: The git instance.
            strict: If set to False, will not compare hash if modified time is the same.

        Returns:
            callback_success: Callback to save the meta file on success case.
            callback_fail: Delete the remote file on failing case.
            tracked_commit: Commit hash of the file if it is tracked.
        """
        rel_path = os.path.relpath(path, self.server_dir)
        if rel_path.startswith(".git/"):
            return None, None, None

        if not self.file_filter(rel_path, path):
            # Skip file if it doesn't match the file filter
            return None, None, None

        # Check if meta exists
        meta_path = self._get_abs_meta_path(rel_path)
        if os.path.exists(meta_path):
            meta = FileMeta.from_meta(meta_path)
            # Skip if meta is up to date
            if meta.validate(path, strict):
                return None, None, git.get_latest_hash(self._get_rel_path(meta_path))

        logging.info("Pushing file %s", rel_path)
        if not git.is_ignored(rel_path):
            git.rm_cached(rel_path)
        
        # Update meta
        remote_path = self.get_remote_path(prefix, rel_path)

        op_path = path
        has_tmp = False
        processor = self.file_processor_selector(path)
        if processor is not None:
            op_path = self._get_abs_tmp_path(rel_path)
            os.makedirs(os.path.dirname(op_path), exist_ok=True)
            has_tmp = True
            processor.process(path, op_path)

        # Push to storage
        self.storage.store(
            local_path_list=op_path,
            remote_path_list=[remote_path]
        )
        
        def save_meta():
            meta = FileMeta.from_file(remote_path=remote_path, file_path=op_path, processor=processor)
            meta.to_meta(meta_path)
            if has_tmp:
                os.remove(op_path)

        def delete_remote():
            self.delete_remote(remote_path)

        return save_meta, delete_remote, "HEAD"

    def pull_all(self, strict: bool = False):
        """Update local server directory.

        Args:
            strict: If set to False, will not compare hash if modified time is the same.
        """
        callback_succ_list: List[Callable[[], None]] = []
        callback_fail_list: List[Callable[[], None]] = []
        try:
            for root, _dirs, files in tqdm(os.walk(self.server_dir), desc="Pulling files"):
                for file in tqdm(files, desc=root, leave=False):
                    path = os.path.join(root, file)
                    callback_succ, callback_fail = self.pull_file(path, strict)
                    if callback_succ is not None:
                        callback_succ_list.append(callback_succ)
                    if callback_fail is not None:
                        callback_fail_list.append(callback_fail)
        except FileHashMismatchException as e:
            logging.error("Hash mismatch for file %s, aborting.", e.path)
            for callback_fail in callback_fail_list:
                callback_fail()
        except Exception as e:
            logging.error("Failed to pull file %s, aborting.", path)
            logging.exception(e)
            for callback_fail in callback_fail_list:
                callback_fail()
        else:
            for callback_succ in callback_succ_list:
                callback_succ()

    def delete_remote(self, *remote_paths: List[str]):
        """Delete the given path from the remote storage."""
        self.storage.delete(remote_path_list=remote_paths)

    def retrieve_metadata(self) -> Optional[dict]:
        remote_path = self.storage.join_path(self.remote_root, "metadata.json")
        if not self.storage.exists(remote_path):
            return None
        else:
            self.storage.retrieve(remote_path_list=[remote_path], local_path_list=[self.get_metadata_file_tmp_path()])
            with open(self.get_metadata_file_tmp_path(), "r", encoding="utf-8") as f:
                retval = json.load(f)
            os.remove(self.get_metadata_file_tmp_path())
            return retval
    
    def store_metadata(self, metadata: dict):
        with open(self.get_metadata_file_tmp_path(), "w", encoding="utf-8") as f:
            json.dump(metadata, f)
        self.storage.store(local_path_list=[self.get_metadata_file_tmp_path()], remote_path_list=[self.storage.join_path(self.remote_root, "metadata.json")])
        os.remove(self.get_metadata_file_tmp_path())

    def get_metadata_file_tmp_path(self) -> str:
        return self._get_abs_path(os.path.join("tmp", "metadata.json"))