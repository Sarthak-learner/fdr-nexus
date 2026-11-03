"""Run maturity reminder generation once.

Schedule this command with the host scheduler (for example, Windows Task
Scheduler) rather than relying on a browser or an unconfigured background
worker:

    python -m app.commands.generate_reminders
"""

from app.database import SessionLocal
from app.services.audit import log_system
from app.services.reminders import generate_maturity_reminders


def main():
    with SessionLocal.begin() as db:
        result = generate_maturity_reminders(db)
        log_system(
            db,
            "reminder.generate",
            "maturity_reminder",
            None,
            f"{result['created']} created, {result['superseded']} superseded, {result['examined']} FDRs examined",
        )
    print(
        "Maturity reminder run completed: "
        f"{result['created']} created, {result['superseded']} superseded, "
        f"{result['examined']} FDRs examined."
    )


if __name__ == "__main__":
    main()
