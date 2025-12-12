import bz2

from mcsg.processor import Processor

class BzipProcessor(Processor):
    def process(self, path: str, output_path: str):
        with open(path, "rb") as f:
            data = f.read()
        with open(output_path, "wb") as f:
            f.write(bz2.compress(data))

    def unprocess(self, path: str, output_path: str):
        with open(path, "rb") as f:
            data = f.read()
        with open(output_path, "wb") as f:
            f.write(bz2.decompress(data))