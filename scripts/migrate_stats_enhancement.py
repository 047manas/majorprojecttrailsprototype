import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import StudentActivity
from sqlalchemy import text

app = create_app()

def migrate():
    with app.app_context():
        print("Migrating StudentActivity table...")
        
        # 1. Add Columns if they don't exist
        with db.engine.connect() as conn:
            trans = conn.begin()
            try:
                # specific to Postgres/SQLite, assuming Postgres based on config
                # But let's check if column exists first to be safe or use IF NOT EXISTS if supported
                # Using simple ALTER TABLE with exception handling is often easiest for scripts without alembic
                
                try:
                    conn.execute(text("ALTER TABLE student_activities ADD COLUMN organizer VARCHAR(200)"))
                    print("Added column: organizer")
                except Exception as e:
                    print(f"Column 'organizer' might already exist: {e}")

                try:
                    conn.execute(text("ALTER TABLE student_activities ADD COLUMN issue_date DATE"))
                    print("Added column: issue_date")
                except Exception as e:
                    print(f"Column 'issue_date' might already exist: {e}")
                
                trans.commit()
            except Exception as e:
                trans.rollback()
                print(f"Migration failed during column addition: {e}")
                return

        # 2. Backfill Data
        # Map issuer_name -> organizer
        # Map end_date (or created_at) -> issue_date
        print("Backfilling data...")
        activities = StudentActivity.query.all()
        count = 0
        for act in activities:
            changed = False
            if not act.organizer and act.issuer_name:
                act.organizer = act.issuer_name
                changed = True
            
            if not act.issue_date:
                # Prefer end_date, else created_at date
                if act.end_date:
                    act.issue_date = act.end_date
                    changed = True
                else:
                    act.issue_date = act.created_at.date()
                    changed = True
            
            if changed:
                count += 1
        
        if count > 0:
            db.session.commit()
            print(f"Backfilled {count} records.")
        else:
            print("No records needed backfilling.")

if __name__ == "__main__":
    migrate()
