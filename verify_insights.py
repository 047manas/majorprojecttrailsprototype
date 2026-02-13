
from unittest.mock import patch, MagicMock
from app import create_app

app = create_app()

def run_verification():
    print("--- Starting Verification (Admin Role) ---")
    
    # Patch current_user in the service module
    with patch('app.services.analytics_service.current_user') as mock_user:
        mock_user.is_authenticated = True
        mock_user.role = 'admin'
        mock_user.department = 'CSE' # Dummy
        
        from app.services.analytics_service import AnalyticsService
        
        with app.app_context():
            print("--- 1. Testing Admin Insights ---")
            try:
                insights = AnalyticsService.get_admin_insights()
                print("Insights Keys:", list(insights.keys()))
                print(f"Top Dept: {insights.get('top_dept')} ({insights.get('top_dept_val')}%)")
                print(f"Risk Events: {len(insights.get('risk_events'))} found")
            except Exception as e:
                print(f"ERROR insights: {e}")
            
            print("\n--- 2. Testing Data Health ---")
            try:
                health = AnalyticsService.get_data_health_summary()
                print(f"Date Health: {health}")
            except Exception as e:
                 print(f"ERROR health: {e}")
            
            print("\n--- 3. Testing Comparative Stats (Year 2025) ---")
            try:
                # Assuming data exists for 2025 and 2024
                comp = AnalyticsService.get_comparative_stats({'year': 2025})
                if comp:
                    print("Comparison Keys:", list(comp.keys()))
                    label = comp['total_events'].get('label', 'N/A')
                    print(f"Events Growth Label: {label}")
                else:
                    print("No Comparison Data (or Year missing)")
            except Exception as e:
                print(f"ERROR comparison: {e}")
                
            print("\n--- 4. Testing Drilldown (Student List for Category) ---")
            try:
                # Fetch distribution to get a category
                dist = AnalyticsService.get_event_distribution()
                if dist and len(dist) > 0:
                    first_cat = dist[0]
                    cat_name = first_cat['category']
                    print(f"Drilling down into Category: {cat_name}")
                    
                    # Level 1: List Events
                    events = AnalyticsService.get_student_list(category_name=cat_name, per_page=5)
                    print(f"Found {events['total_records']} records for category '{cat_name}'.")
                    
                    if events.get('students'):
                        first_row = events['students'][0]
                        # first_row is a serialized DICT
                        event_title = first_row.get('title')
                        print(f"Sample Event Title: {event_title}")
                        
                        # Level 2: Dept for Event
                        dept_rows = AnalyticsService.get_student_list(search=event_title, per_page=5)
                        print(f"Found {dept_rows['total_records']} records matching title '{event_title}'.")
                else:
                    print("No distribution data found to drill down.")
            except Exception as e:
                print(f"ERROR drilldown: {e}")

if __name__ == "__main__":
    run_verification()
