import argparse

from mcsg.storage_backends.s3 import S3Storage, S3Config
from config import CONFIG

if __name__=="__main__":
    storage = S3Storage(CONFIG.storage_config)
    
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["delete"])
    parser.add_argument("path", type=str)
    args = parser.parse_args()
    if args.action == "delete":
        storage.delete(storage.list(args.path))
        print("Successfully deleted all files in", args.path)