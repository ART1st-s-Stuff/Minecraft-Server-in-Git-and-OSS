from abc import ABC, abstractmethod
from typing import List, Union
from dataclasses import dataclass
from datetime import datetime

@dataclass
class FileInfo:
    path: str
    filename: str
    size: int
    updated_at: datetime
    hash: str

@dataclass
class DirInfo:
    path: str
    updated_at: datetime

class RemoteStorage(ABC):
    @abstractmethod
    def store(self, local_path: str, remote_path: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def retrieve(self, remote_path: str, local_path: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, remote_path: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def list(self, remote_path: str) -> List[Union[FileInfo, DirInfo]]:
        raise NotImplementedError

    @abstractmethod
    def join_path(self, *paths: str) -> str:
        raise NotImplementedError