/**
 * Forms Interaction Logic
 * Handles dynamic field toggling for Student and Admin forms.
 */

/* Student Dashboard: Toggle Custom Category for 'Other' activity type */
function toggleCustomCategory() {
    var select = document.getElementById('activity_type_select');
    var customGroup = document.getElementById('custom_category_group');
    var customInput = document.getElementById('custom_category');

    if (!select || !customGroup || !customInput) return;

    if (select.value === 'other') {
        customGroup.style.display = 'block';
        customInput.required = true;
    } else {
        customGroup.style.display = 'none';
        customInput.required = false;
        customInput.value = '';
    }
}

/* Admin User Management: Toggle fields based on Role */
function toggleFields() {
    const roleSelect = document.getElementById('role');
    const extraFields = document.getElementById('extra-fields');
    const instIdLabel = document.getElementById('inst-id-label');
    const deptInput = document.getElementById('department');
    const instIdInput = document.getElementById('institution_id');
    const positionField = document.getElementById('position-field');

    if (!roleSelect) return;

    const role = roleSelect.value;

    if (role === 'admin') {
        extraFields.style.display = 'contents';
        if (positionField) positionField.style.display = 'none';
        if (deptInput) deptInput.required = false;
        if (instIdInput) instIdInput.required = false;
        if (instIdLabel) instIdLabel.innerText = "Institution ID (Optional)";
    } else if (role === 'faculty') {
        extraFields.style.display = 'contents';
        if (positionField) positionField.style.display = 'block';
        if (deptInput) deptInput.required = true;
        if (instIdInput) instIdInput.required = true;
        if (instIdLabel) instIdLabel.innerText = "Institution ID (Faculty ID)";
    } else if (role === 'student') {
        extraFields.style.display = 'contents';
        if (positionField) positionField.style.display = 'none';
        if (deptInput) deptInput.required = true;
        if (instIdInput) instIdInput.required = true;
        if (instIdLabel) instIdLabel.innerText = "Institution ID (Roll Number)";
    }
}

// Global Event Listeners
document.addEventListener('DOMContentLoaded', function () {
    // Attach listeners if elements exist
    const activitySelect = document.getElementById('activity_type_select');
    if (activitySelect) {
        activitySelect.addEventListener('change', toggleCustomCategory);
        // Initial check
        toggleCustomCategory();
    }

    const roleSelect = document.getElementById('role');
    if (roleSelect) {
        roleSelect.addEventListener('change', toggleFields);
        // Initial check (window.onload replacement)
        toggleFields();
    }
});
