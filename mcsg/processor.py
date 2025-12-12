from abc import ABC, abstractmethod

class Processor(ABC):
    @abstractmethod
    def process(self, path: str, output_path: str):
        raise NotImplementedError

    @abstractmethod
    def unprocess(self, path: str, output_path: str):
        raise NotImplementedError