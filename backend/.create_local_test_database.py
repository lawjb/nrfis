import csv
import json

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from database_models import Base, Basement, StrongFloor, SteelFrame
from database_models.metadata import (
    BasementMetadata,
    StrongFloorMetadata,
    SteelFrameMetadata,
)

DATABASE_URL = "postgresql+psycopg2://postgres:@localhost/timescaletest"
db = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db)

Base.metadata.create_all(db)

session = SessionLocal()

with open(
    "backend/database_models/test_data/basement_fbg_metadata.csv", encoding="utf-8-sig"
) as csvfile:
    data = csv.DictReader(csvfile)
    for row in data:
        row["recording"] = row["recording"] == "TRUE"
        row["coeffs"] = json.loads(row["coeffs"] or "null")
        session.add(BasementMetadata(**{k: v for k, v in row.items() if v != ""}))
        session.commit()

with open(
    "backend/database_models/test_data/strong_floor_fbg_metadata.csv",
    encoding="utf-8-sig",
) as csvfile:
    data = csv.DictReader(csvfile)
    for row in data:
        row["recording"] = row["recording"] == "TRUE"
        row["coeffs"] = json.loads(row["coeffs"] or "null")
        session.add(StrongFloorMetadata(**{k: v for k, v in row.items() if v != ""}))
        session.commit()

with open(
    "backend/database_models/test_data/steel_frame_fbg_metadata.csv",
    encoding="utf-8-sig",
) as csvfile:
    data = csv.DictReader(csvfile)
    for row in data:
        row["recording"] = row["recording"] == "TRUE"
        row["coeffs"] = json.loads(row["coeffs"] or "null")
        session.add(SteelFrameMetadata(**{k: v for k, v in row.items() if v != ""}))
        session.commit()

session.commit()

with db.connect() as conn:
    conn.execute(text("SELECT create_hypertable('basement_fbg', 'timestamp')"))
    conn.execute(text("SELECT create_hypertable('strong_floor_fbg', 'timestamp')"))
    conn.execute(text("SELECT create_hypertable('steel_frame_fbg', 'timestamp')"))

with open(
    "backend/database_models/test_data/basement_fbg.csv", encoding="utf-8-sig"
) as csvfile:
    data = csv.DictReader(csvfile)
    for row in data:
        session.add(Basement(**row))

with open(
    "backend/database_models/test_data/strong_floor_fbg.csv", encoding="utf-8-sig",
) as csvfile:
    data = csv.DictReader(csvfile)
    for row in data:
        session.add(StrongFloor(**row))

with open(
    "backend/database_models/test_data/steel_frame_fbg.csv", encoding="utf-8-sig",
) as csvfile:
    data = csv.DictReader(csvfile)
    for row in data:
        session.add(SteelFrame(**row))

session.commit()
session.close()
