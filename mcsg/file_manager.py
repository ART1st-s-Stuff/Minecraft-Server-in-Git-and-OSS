from dataclasses import dataclass
from typing import Tuple, Callable, List, Optional
import os
import json
import hashlib
from subprocess import CalledProcessError
import logging
from datetime import datetime

from mcsg.storage import RemoteStorage, DirInfo
from mcsg.git import Git

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

    @classmethod
    def from_meta(cls, meta_path: str) -> "FileMeta":
        with open(meta_path, "r", encoding="utf-8") as f:
            return cls(**json.load(f))

    @classmethod
    def from_file(cls, remote_path: str, file_path: str) -> "FileMeta":
        with open(file_path, "rb") as f:
            return cls(remote_path, hashlib.sha256(f.read()).hexdigest(), os.path.getmtime(file_path))
    
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
    git: Git
    file_filter: Callable[[str, str], bool]     # Input 1: relative path, Input 2: absolute path

    def __init__(self, storage: RemoteStorage, server_dir: str, remote_root: str, file_filter: Callable[[str, str], bool]):
        self.storage = storage
        self.server_dir = server_dir
        self.remote_root = remote_root
        self.file_filter = file_filter
        self.git = Git(server_dir)

    def _get_hash(self, path: str) -> str:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def _pull_file(self, path: str, strict: bool = False) -> Tuple[Optional[Callable[[], None]], Optional[Callable[[], None]]]:
        """Pull from remote storage to local server directory.

        Args:
            path: The path to the file.
            strict: If set to False, will not compare hash if modified time is the same.

        Returns:
            callback_success: Callback to replace the local file with the temporary file on success case.
            callback_fail: Callback to delete the temporary file on failing case.
        """
        meta_path = path + ".meta"
        tmp_path = path + ".tmp"
        if not os.path.exists(meta_path):
            return None, None

        meta = FileMeta.from_meta(meta_path)
        if meta.validate(path, strict):
            return None, None
        
        logging.info("Pulling file %s", path)
        self.storage.retrieve(
            local_path=tmp_path,
            remote_path=meta.remote_path
        )

        if self._get_hash(tmp_path) != meta.hash:
            raise FileHashMismatchException(path)

        return lambda: (os.remove(path), os.rename(tmp_path, path)), lambda: os.remove(tmp_path)

    def _push_file(self, prefix: str, path: str, strict: bool = False) -> Tuple[Optional[Callable[[], None]], Optional[Callable[[], None]]]:
        """Push the file to the remote storage and update the meta file.

        Args:
            prefix: The prefix for the remote path.
            path: The path to the file.
            strict: If set to False, will not compare hash if modified time is the same.

        Returns:
            callback_success: Callback to save the meta file on success case.
            callback_fail: Not used by now.
        """
        rel_path = os.path.relpath(path, self.server_dir)
        if rel_path.startswith(".git/"):
            return None, None

        if not self.file_filter(rel_path, path):
            # Skip file if it doesn't match the file filter
            return None, None

        # Check if meta exists
        meta_path = path + ".meta"
        if os.path.exists(meta_path):
            meta = FileMeta.from_meta(meta_path)
            # Skip if meta is up to date
            if meta.validate(path, strict):
                return None, None

        logging.info("Pushing file %s", rel_path)
        if not self.git.is_ignored(rel_path):
            self.git.rm_cached(rel_path)
        
        # Update meta
        remote_path = self.storage.join_path(self.remote_root, prefix, path)

        # Push to storage
        self.storage.store(
            local_path=path,
            remote_path=remote_path
        )
        
        def save_meta():
            meta = FileMeta.from_file(remote_path=remote_path, file_path=path)
            meta.to_meta(meta_path)
        return save_meta, None

    def pull(self, strict: bool = False):
        """Pull from git and update local server directory.

        Args:
            strict: If set to False, will not compare hash if modified time is the same.
        """
        try:
            self.git.pull()
        except CalledProcessError as e:
            logging.error("Command `git pull` failed.")
            logging.error(e.stdout)
            logging.error(e.stderr)
            logging.error("Please check the git repository and try again.")
            return
        
        callback_succ_list: List[Callable[[], None]] = []
        callback_fail_list: List[Callable[[], None]] = []
        try:
            for root, _dirs, files in tqdm(os.walk(self.server_dir), desc="Pulling files"):
                for file in tqdm(files, desc=root, leave=False):
                    path = os.path.join(root, file)
                    callback_succ, callback_fail = self._pull_file(path, strict)
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

    def push(self, strict: bool = False):
        """Push the files to the remote storage and commit the changes.

        Args:
            strict: If set to False, will not compare hash if modified time is the same.
        """
        commit_time = datetime.now()
        prefix = str(int(commit_time.timestamp())) + "-" + self.git.last_commit_hash()
        callback_succ_list: List[Callable[[], None]] = []
        callback_fail_list: List[Callable[[], None]] = []
        try:
            self.git.reset(".")
            self.git.add(".")
            for root, _dirs, files in tqdm(os.walk(self.server_dir), desc="Pushing files"):
                for file in tqdm(files, desc=root, leave=False):
                    path = os.path.join(root, file)
                    callback_succ, callback_fail = self._push_file(prefix=prefix, path=path, strict=strict)
                    if callback_succ is not None:
                        callback_succ_list.append(callback_succ)
                    if callback_fail is not None:
                        callback_fail_list.append(callback_fail)
            self.git.commit(f"Update files at {commit_time.strftime('%Y-%m-%d %H:%M:%S')}")
            self.git.push()
        except CalledProcessError as e:
            self.git.reset(".")
            for callback_fail in callback_fail_list:
                callback_fail()
            logging.exception("Push failed.")
            logging.error(e.stdout)
            logging.error(e.stderr)
            logging.error("Push operation aborted.")
        except Exception as e:
            self.git.reset(".")
            for callback_fail in callback_fail_list:
                callback_fail()
            logging.exception("Failed to push files. Exception: %s", e)
        else:
            for callback_succ in callback_succ_list:
                callback_succ()

    def clean_remote(self, time: datetime):
        """Clean remote storage by deleting directories created before the given time.

        Args:
            time: The time to clean the remote storage.
        """
        prefix = int(time.timestamp())
        for dir_or_file in self.storage.list(self.remote_root):
            if isinstance(dir_or_file, DirInfo):
                try:
                    dir_name = dir_or_file.path.split("/")[-1]
                    if not dir_name.isdigit() or "-" not in dir_name:
                        logging.warning("Invalid directory name %s, skipping.", dir_name)
                    dir_time = int(dir_name.split("-")[0])    # We use timestamp directly as the directory name
                    if dir_time < prefix:
                        self.storage.delete(dir_or_file.path)
                        logging.info("Deleted remote directory %s created at %s", dir_name, datetime.fromtimestamp(dir_time).strftime("%Y-%m-%d %H:%M:%S"))
                except Exception as e:
                    logging.exception("Failed to delete remote directory %s, skipping. Exception: %s", dir_or_file.path, e)
            else:
                logging.warning("Unexpected file %s, skipping.", dir_or_file.path.split("/")[-1])