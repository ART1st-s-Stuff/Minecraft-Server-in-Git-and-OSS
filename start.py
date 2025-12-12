from datetime import datetime, timedelta
import argparse
from typing import Optional

from mcsg.config import create_commit_manager
from mcsg.processors.bzip import BzipProcessor
from config import CONFIG

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["pull", "push", "clean", "snapshot", "reset", "log"])

    parser.add_argument("--strict", action="store_true", help="Strict mode: Whether to believe modification time when pulling/pushing.")

    parser.add_argument("--before", type=int, help="Clean remote files created before this number of days.")

    parser.add_argument("--name", type=str, help="Name of the snapshot.")
    parser.add_argument("--message", type=str, help="Message of the snapshot.")

    parser.add_argument("--commit", type=str, help="Commit hash.")

    parser.add_argument("--tag", type=str, help="Tag to reset to.")

    args = parser.parse_args()
    commit_manager = create_commit_manager(CONFIG)
    if args.action == "pull":
        commit_manager.pull(strict=args.strict)
    elif args.action == "push":
        commit_manager.push(strict=args.strict)
    elif args.action == "snapshot":
        if args.name is None:
            args.name = datetime.now().strftime("Snapshot %Y-%m-%d_%H-%M-%S")
        if args.message is None:
            args.message = ""
        commit_manager.snapshot(name=args.name, message=args.message, commit=args.commit)
    elif args.action == "reset":
        commit_manager.reset_to_tag(name=args.name)
    elif args.action == "log":
        print("Created at\tCommit\tIs Safe\tSnapshot Tag\tSnapshot Message")
        for commit, info in commit_manager.commits.items():
            if info.is_snapshot:
                snapshot_tag = commit_manager.git.get_tag_hash(commit)
                snapshot_message = commit_manager.git.get_tag_message(snapshot_tag)
                snapshot_str = f"{snapshot_tag}\t{snapshot_message}"
            else:
                snapshot_str = "\t"
            print(f"{datetime.fromtimestamp(info.timestamp).strftime('%Y-%m-%d %H:%M:%S')}\t{commit}\t{'Safe' if info.is_safe else ''}\t{snapshot_str}")
    elif args.action == "clean":
        if args.before is None:
            parser.error("--before must be provided")
        before_time = datetime.now() - timedelta(days=args.before)
        commit_manager.delete(*commit_manager.filter_stale_commits(time=before_time))