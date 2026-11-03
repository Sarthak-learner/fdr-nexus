"""DEVELOPMENT-ONLY seed data. All names are fictional. NOT AICTE data. Run: python dev_seed/dev_seed.py"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from datetime import date, timedelta
from app.database import SessionLocal, Base, engine
from app import models as m
Base.metadata.create_all(engine)
db = SessionLocal()
i = m.Institution(name="DEV-SEED Sample Institute", aicte_id="DEV-0001", city="Sampletown", state="Dev", source="dev-seed")
db.add(i); db.flush()
for n, off in enumerate([-30, 20, 400]):
    db.add(m.FDRRecord(institution_id=i.id, bank_name="Sample Bank", branch="Main", reference_no=f"DEV-FDR-{n}", amount=100000 * (n + 1),
                       issue_date=date.today() - timedelta(days=365), maturity_date=date.today() + timedelta(days=off), source="dev-seed"))
db.commit(); print("Dev seed added.")
