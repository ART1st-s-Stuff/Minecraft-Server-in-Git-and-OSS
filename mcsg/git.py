import subprocess
from typing import List
import os

class Git:
    def __init__(self, repository_path: str):
        self.repository_path = repository_path
        if not os.path.exists(self.repository_path):
            os.makedirs(self.repository_path)
        if not os.path.exists(os.path.join(self.repository_path, ".git")):
            raise ValueError("Not a git repository")

    def _run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["git", *args], capture_output=True, text=True, check=check, cwd=self.repository_path)

    def pull(self):
        return self._run("pull")

    def push(self):
        return self._run("push")

    def add(self, *directory: List[str]):
        return self._run("add", *directory)

    def commit(self, message: str):
        return self._run("commit", "-m", message)

    def reset(self, *directories: List[str], commit: str="HEAD"):
        return self._run("reset", commit, *directories)

    def last_commit_hash(self) -> str:
        return self._run("rev-parse", "HEAD").stdout.strip()
    
    def rm_cached(self, *files: List[str]):
        return self._run("rm", "--cached", *files)

    def is_ignored(self, path: str) -> bool:
        return self._run("check-ignore", path, check=False).returncode == 0

    def tag(self, name: str, commit: str, message: str):
        return self._run("tag", name, commit, "-m", message)

    def get_latest_hash(self, path: str) -> str:
        return self._run("log", "-1", "--format=%H", "--", path).stdout.strip()

    def get_tag_hash(self, name: str) -> str:
        return self._run("rev-parse", name).stdout.strip()

    def get_tag_message(self, name: str) -> str:
        return self._run("tag", "-l", name, "--format=%(contents)").stdout.strip()