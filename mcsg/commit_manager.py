from dataclasses import dataclass
from typing import List, Dict, Callable
from tqdm import tqdm
import os
from datetime import datetime
from subprocess import CalledProcessError

import logging

from mcsg.git import Git
from mcsg.file_manager import FileManager

@dataclass
class CommitInfo:
    timestamp: int
    is_snapshot: bool
    is_safe: bool

@dataclass
class FileCommit:
    commit: str
    depended_by: List[str]

class CommitManager:
    commits: Dict[str, CommitInfo]
    file_history: Dict[str, List[FileCommit]]

    git: Git
    file_manager: FileManager

    def __init__(self, server_root: str, file_manager: FileManager):
        os.makedirs(os.path.join(server_root, "meta"), exist_ok=True)
        os.makedirs(os.path.join(server_root, "tmp"), exist_ok=True)

        self.git = Git(server_root)
        self.file_manager = file_manager

    def load_metadata(self):
        metadata_json = self.file_manager.retrieve_metadata()
        if metadata_json is None:
            self.commits = {}
            self.file_history = {}
        else:
            self.commits = { commit["commit"]: CommitInfo(timestamp=commit["timestamp"], is_snapshot=commit["is_snapshot"], is_safe=commit["is_safe"]) for commit in metadata_json["commits"] }
            self.file_history = { file: [FileCommit(commit=commit["commit"], depended_by=commit["depended_by"]) for commit in metadata_json["file_history"][file] ] for file in metadata_json["file_history"] }
        
    def save_metadata(self):
        self.file_manager.store_metadata({
            "commits": [{"commit": commit.commit, "timestamp": commit.timestamp, "is_snapshot": commit.is_snapshot, "is_safe": commit.is_safe} for commit in self.commits.values()],
            "file_history": {file: [{"commit": commit.commit, "depended_by": commit.depended_by} for commit in commit_list] for file, commit_list in self.file_history.items()}
        })

    @staticmethod
    def update_metadata(func: Callable):
        def wrapper(self: "CommitManager", *args, **kwargs):
            self.load_metadata()
            ret = func(self, *args, **kwargs)
            self.save_metadata()
            return ret
        return wrapper

    def snapshot(self, name: str, commit: str, message: str):
        """Mark current commit as a snapshot commit."""
        if commit not in self.commits:
            raise ValueError(f"Commit {commit} not found")

        self.git.tag(name=name, commit=commit, message=message)
        self.commits[commit].is_snapshot = True
        self.commits[commit].is_safe = True

    def pull(self, strict: bool = False):
        """Pull from git and update local server directory.

        Args:
            strict: If set to False, will not compare hash if modified time is the same.
        """
        try:
            self.git.pull()
        except CalledProcessError as e:
            logging.exception("Command `git pull` failed.")
            logging.error(e.stdout)
            logging.error(e.stderr)
            logging.error("Please check the git repository and try again.")
            return
        
        self.file_manager.pull_all(strict=strict)

    def reset(self, commit: str, strict: bool = True):
        """Reset the local server directory to the given commit.

        Args:
            commit: The commit hash to reset to.
            strict: If set to False, will not compare hash if modified time is the same.
        """
        if commit not in self.commits:
            raise ValueError(f"Commit {commit} not found")
        if not self.commits[commit].is_safe:
            raise ValueError(f"Commit {commit} is not a safe commit to restore")
        
        try:
            self.git.reset(commit)
        except CalledProcessError as e:
            logging.exception("Command `git reset` failed.")
            logging.error(e.stdout)
            logging.error(e.stderr)
            logging.error("Please check the git repository and try again.")
        else:
            self.file_manager.pull_all(strict=strict)

    def reset_to_tag(self, name: str):
        """Reset the local server directory to the given tag.

        Args:
            name: The name of the tag to reset to.
        """
        try:
            commit = self.git.get_tag_hash(name)
            self.reset(commit)
        except CalledProcessError as e:
            logging.exception("Command `git reset` failed.")
            logging.error(e.stdout)
            logging.error(e.stderr)
            logging.error("Please check the git repository and try again.")

    @update_metadata
    def push(self, strict: bool = False):
        """Push the files to the remote storage and commit the changes.

        Args:
            strict: If set to False, will not compare hash if modified time is the same.
        """
        commit_time = datetime.now()
        last_commit = self.git.last_commit_hash()
        callback_succ_list: List[Callable[[], None]] = []
        callback_fail_list: List[Callable[[], None]] = []
        tracked_commits: Dict[str, str] = {}
        try:
            self.git.reset(".")
            self.git.add(".")
            if not self.git.is_ignored("tmp/"):
                self.git.rm_cached("tmp/")
            for root, _dirs, files in tqdm(os.walk(self.file_manager.server_dir), desc="Pushing files"):
                for file in tqdm(files, desc=root, leave=False):
                    path = os.path.join(root, file)
                    callback_succ, callback_fail, tracked_commit = self.file_manager.push_file(prefix=last_commit, path=path, git=self.git, strict=strict)
                    if callback_succ is not None:
                        callback_succ_list.append(callback_succ)
                    if callback_fail is not None:
                        callback_fail_list.append(callback_fail)
                    if tracked_commit is not None:
                        tracked_commits[file] = tracked_commit
        except CalledProcessError as e:
            self.git.reset(".")
            for callback_fail in callback_fail_list:
                callback_fail()
            logging.exception("Push failed.")
            logging.error(e.stdout)
            logging.error(e.stderr)
            logging.error("Push operation aborted.")
            return
        except Exception as e:
            self.git.reset(".")
            for callback_fail in callback_fail_list:
                callback_fail()
            logging.exception("Failed to push files. Exception: %s", e)
            return
        
        # Update all metas
        for callback_succ in callback_succ_list:
            callback_succ()
        # Push to github
        try:
            self.git.commit(f"Update files at {commit_time.strftime('%Y-%m-%d %H:%M:%S')}")
            commit_hash = self.git.last_commit_hash()
            self.git.push()
        except CalledProcessError as e:
            logging.exception("Command `git commit` failed.")
            logging.error(e.stdout)
            logging.error(e.stderr)
            logging.error("Push operation aborted.")
            return
        # Update metadata
        self.commits[commit_hash] = CommitInfo(timestamp=commit_time.timestamp(), is_snapshot=False, is_safe=True)
        for file, tracked_commit in tracked_commits.items():
            if tracked_commit == "HEAD":
                self.file_history.setdefault(file, []).append(FileCommit(commit=commit_hash, depended_by=[commit_hash]))
            else:
                # Update dependency of the tracked commit
                for commit in self.file_history[file]:
                    if commit.commit == tracked_commit:
                        commit.depended_by.append(commit_hash)
                        break

    @update_metadata
    def delete(self, *commits_to_delete: List[str]):
        """Delete the given commits.
        
        Will keep the commits that are still depended by other commits.

        Args:
            commits_to_delete: The commits to delete.
        """
        commits_to_keep = set([ commit for commit in self.commits if commit not in commits_to_delete ])
        still_tracking_commits = set()
        try:
            for file, commit_list in self.file_history.items():
                new_commit_list = commit_list.copy()
                for file_commit in commit_list:
                    if file_commit.commit in commits_to_delete \
                            and len(commits_to_keep.intersection(file_commit.depended_by)) == 0:
                        # If the commit of a file is to be deleted and not depended by any other commits to keep, it can be safely deleted
                        # Delete remote file during loop. We save immediately in case of failure, to ensure our file history is consistent.
                        self.file_manager.delete_remote(self.file_manager.get_remote_path(prefix=file_commit.commit, rel_path=file))
                        # If failed, the commit will be kept in the file history.
                        new_commit_list.remove(file_commit)
                        self.commits[file_commit.commit].is_safe = False
                    else:
                        # This commit is still depended by other commits, we keep tracking it.
                        still_tracking_commits.add(file_commit.commit)
                self.file_history[file] = new_commit_list
        except Exception as e:
            logging.exception("Failed to delete remote files. Exception: %s", e)
        
        # Trim history
        self.file_history = { file: commit_list for file, commit_list in self.file_history.items() if len(commit_list) > 0 }
        # Remove untracked commits
        untracked_commits = set(commits_to_delete) - still_tracking_commits
        for commit in untracked_commits:
            del self.commits[commit]

    def filter_stale_commits(self, time: datetime):
        """Filter out commits that are older than the given time and are not snapshots."""
        ts = time.timestamp()
        return [ commit for commit, info in self.commits.items() if info.timestamp < ts and not info.is_snapshot ]