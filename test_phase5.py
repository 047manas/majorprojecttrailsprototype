"""Test Phase 5: Advanced Exports & Certificate Access"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from app import create_app
app = create_app()

with app.app_context():
    from app.services.analytics_service import AnalyticsService
    
    # Test 1: get_student_list with certificate fields
    print("=== Test 1: Student List ===")
    result = AnalyticsService.get_student_list(page=1, per_page=3)
    if isinstance(result, dict):
        print(f"  Total records: {result['total_records']}")
        if result['students']:
            s = result['students'][0]
            print(f"  Keys: {list(s.keys())}")
            has_cert = 'certificate_url' in s
            has_mode = 'verification_mode' in s
            print(f"  Has certificate_url: {has_cert}")
            print(f"  Has verification_mode: {has_mode}")
        else:
            print("  No students found")
    else:
        print(f"  ERROR: got {type(result)}")

    # Test 2: get_comparative_stats
    print("\n=== Test 2: Comparative Stats ===")
    comp = AnalyticsService.get_comparative_stats({'year': 2024})
    if comp:
        print(f"  Keys: {list(comp.keys())}")
        print(f"  Current year: {comp['current_year']}")
        print(f"  Events growth: {comp['total_events']}")
    else:
        print("  Returned None (expected if no 2024 data)")

    # Test 3: generate_snapshot_export
    print("\n=== Test 3: Snapshot Export ===")
    try:
        output = AnalyticsService.generate_snapshot_export(filters={})
        print(f"  Success! Size: {output.getbuffer().nbytes} bytes")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Test 4: generate_filtered_student_export
    print("\n=== Test 4: Filtered Student Export ===")
    try:
        output2 = AnalyticsService.generate_filtered_student_export(department='CSE')
        print(f"  Success! Size: {output2.getbuffer().nbytes} bytes")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Test 5: generate_event_instance_export
    print("\n=== Test 5: Event Instance Export ===")
    try:
        output3 = AnalyticsService.generate_event_instance_export('TYPE-1-2024-01-01')
        print(f"  Success! Size: {output3.getbuffer().nbytes} bytes")
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n=== ALL TESTS COMPLETE ===")
