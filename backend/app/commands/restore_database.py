"""Restore a verified SQLite backup to a target path.

The command refuses to overwrite an existing file unless --force is given.
Use a temporary target for recovery testing; stop the application before any
operator-approved live restore.
"""

import argparse

from app.services.backup import restore_database


def main():
    parser = argparse.ArgumentParser(description="Restore a verified FDR Nexus SQLite backup")
    parser.add_argument("backup", help="Path to a verified backup file")
    parser.add_argument("target", help="Target SQLite database path")
    parser.add_argument("--force", action="store_true", help="Allow replacement of an existing target")
    args = parser.parse_args()
    result = restore_database(args.backup, args.target, overwrite=args.force)
    print(f"Restore completed: {result['path']}")
    print(f"Integrity: {result['integrity']}; pages: {result['page_count']}")


if __name__ == "__main__":
    main()
