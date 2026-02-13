from app import create_app, db
from app.models import StudentActivity
from sqlalchemy import func, case, literal

app = create_app()

with app.app_context():
    def get_identity_expr():
        # Match the new logic in AnalyticsService
        return case(
            (StudentActivity.activity_type_id.isnot(None),
             func.concat(StudentActivity.activity_type_id, '-', func.coalesce(func.cast(StudentActivity.start_date, db.String), 'nodate'))),
            else_=func.concat(func.coalesce(StudentActivity.custom_category, 'other'), '-', func.lower(func.trim(StudentActivity.title)), '-', func.coalesce(func.cast(StudentActivity.start_date, db.String), 'nodate'))
        )

    results = db.session.query(
        StudentActivity.id,
        StudentActivity.title,
        StudentActivity.activity_type_id,
        StudentActivity.start_date,
        get_identity_expr().label('identity')
    ).all()
    
    with open('identities_v2.log', 'w') as f:
        f.write(f"{'ID':<5} | {'Type':<5} | {'Date':<12} | {'Title':<20} | {'Calculated Identity'}\n")
        f.write("-" * 80 + "\n")
        unique_ids = set()
        for r in results:
            f.write(f"{r.id:<5} | {r.activity_type_id:<5} | {str(r.start_date):<12} | {r.title:<20} | {r.identity}\n")
            unique_ids.add(r.identity)
        f.write("-" * 80 + "\n")
        f.write(f"Total Unique Identities: {len(unique_ids)}\n")
        f.write(f"Unique Identities Set: {unique_ids}\n")
