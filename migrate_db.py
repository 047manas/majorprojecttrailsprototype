import os
from sqlalchemy import create_engine, text

# Get DB URI from config (hardcoded for now based on config.py view)
DB_URI = "postgresql://postgres:root%40123@localhost:5432/smarthub"

def migrate():
    engine = create_engine(DB_URI)
    with engine.connect() as conn:
        # 1. Add batch_year to users
        try:
            print("Attempting to add batch_year to users...")
            conn.execute(text("ALTER TABLE users ADD COLUMN batch_year VARCHAR(20)"))
            print("Successfully added batch_year to users.")
        except Exception as e:
            print(f"Skipping users.batch_year (might exist): {e}")

        # 2. Add approved_at to student_activities
        try:
            print("Attempting to add approved_at to student_activities...")
            conn.execute(text("ALTER TABLE student_activities ADD COLUMN approved_at TIMESTAMP"))
            print("Successfully added approved_at to student_activities.")
        except Exception as e:
            print(f"Skipping student_activities.approved_at (might exist): {e}")
            
        conn.commit()

if __name__ == "__main__":
    migrate()
