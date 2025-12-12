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
    def store(self, local_path_list: List[str], remote_path_list: List[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    def retrieve(self, remote_path_list: List[str], local_path_list: List[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    def delete(self, remote_path_list: List[str]) -> None:
        raise NotImplementedError

    @abstractmethod
    def exists(self, remote_path: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def join_path(self, *paths: str) -> str:
        raise NotImplementedError