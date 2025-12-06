from datetime import datetime, timedelta
import argparse

from mcsg.config import create_file_manager

from config import CONFIG

def pull(strict: bool = False):
    file_manager = create_file_manager(CONFIG)
    file_manager.pull(strict=strict)

def push(strict: bool = False):
    file_manager = create_file_manager(CONFIG)
    file_manager.push(strict=strict)

def clean(time: datetime):
    file_manager = create_file_manager(CONFIG)
    file_manager.clean_remote(time=time)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["pull", "push", "clean"])
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--before", type=int, help="Clean remote files created before this number of days.")
    args = parser.parse_args()
    if args.action == "pull":
        pull(strict=args.strict)
    elif args.action == "push":
        push(strict=args.strict)
    elif args.action == "clean":
        if args.before is None:
            parser.error("--before must be provided")
        before_time = datetime.now() - timedelta(days=args.before)
        clean(time=before_time)