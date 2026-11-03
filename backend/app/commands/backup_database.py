"""Create and verify a timestamped SQLite backup.

Example:
    python -m app.commands.backup_database --output-dir data/backups
"""

import argparse

from app.services.backup import backup_database


def main():
    parser = argparse.ArgumentParser(description="Create a verified FDR Nexus SQLite backup")
    parser.add_argument("--output-dir", help="Directory for the timestamped backup")
    args = parser.parse_args()
    result = backup_database(output_dir=args.output_dir)
    print(f"Backup created: {result['path']}")
    print(f"Integrity: {result['integrity']}; pages: {result['page_count']}")


if __name__ == "__main__":
    main()
