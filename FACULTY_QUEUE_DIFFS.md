# Faculty Queue - Template & CSS Diffs

## File 1: New Queue Template (`templates/faculty_queue.html`)

### Purpose
Display all pending certificates in a clean, sortable table format.

### Key Sections

#### Header
```html
<header>
    <div class="d-flex justify-content-between align-items-center">
        <div>
            <h1>Faculty Dashboard</h1>
            <p class="text-muted">Review pending verification requests assigned to you.</p>
        </div>
        <div class="header-user-section">
            <div class="user-info">
                <strong>{{ current_user.full_name }}</strong>
                <small>{{ current_user.department or 'N/A' }} | ID: {{ current_user.institution_id or 'N/A' }}</small>
            </div>
        </div>
    </div>
</header>
```

#### Queue Table
```html
<div class="mb-4">
    <h2>Verification Queue</h2>
    <p class="text-muted">{{ pending_requests | length }} pending certificate{{ '' if pending_requests | length == 1 else 's' }} awaiting review</p>
</div>

<div class="table-responsive">
    <table class="queue-table">
        <thead>
            <tr>
                <th>Student Name</th>
                <th>Roll Number</th>
                <th>Activity / Certificate</th>
                <th>Uploaded Date</th>
                <th>Status</th>
                <th class="action-col">Action</th>
            </tr>
        </thead>
        <tbody>
            {% for req in pending_requests %}
            <tr class="queue-row">
                <td>{{ req.student.full_name }}</td>
                <td><code>{{ req.student.institution_id }}</code></td>
                <td>
                    <div class="activity-title">{{ req.title }}</div>
                    {% if req.activity_type %}
                    <span class="badge-small bg-secondary">{{ req.activity_type.name }}</span>
                    {% else %}
                    <span class="badge-small bg-secondary">{{ req.custom_category }}</span>
                    {% endif %}
                </td>
                <td class="date-cell">{{ req.created_at.strftime('%b %d, %Y') if req.created_at else 'N/A' }}</td>
                <td>
                    <span class="status-badge status-pending">Pending Review</span>
                </td>
                <td class="action-col">
                    <a href="{{ url_for('faculty_review', act_id=req.id) }}" class="btn btn-sm btn-primary">
                        View Details
                    </a>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
</div>
```

### Jinja2 Variables Used
- `pending_requests` - List of StudentActivity objects
- `current_user.full_name`, `.department`, `.institution_id` - Faculty info
- `req.student.full_name`, `.institution_id` - Student details
- `req.title`, `.activity_type.name`, `.custom_category` - Activity info
- `req.created_at` - Upload timestamp
- `url_for('faculty_review', act_id=req.id)` - Link to detail page

---

## File 2: New Detail Review Template (`templates/faculty_review.html`)

### Purpose
Show full certificate details with side-by-side approval/rejection forms.

### Key Sections

#### Navigation & Header
```html
<header>
    <div class="d-flex justify-content-between align-items-center">
        <div>
            <a href="{{ url_for('faculty_dashboard') }}" class="btn btn-sm btn-outline-secondary mb-2">← Back to Queue</a>
            <h1>Certificate Review</h1>
            <p class="text-muted">Activity #{{ activity.id }} | Student: {{ activity.student.full_name }}</p>
        </div>
        <div class="header-user-section">
            <div class="user-info">
                <strong>{{ current_user.full_name }}</strong>
                <small>{{ current_user.department or 'N/A' }} | ID: {{ current_user.institution_id or 'N/A' }}</small>
            </div>
        </div>
    </div>
</header>
```

#### Certificate Details (Left Column)
```html
<div class="grid-2">
    <!-- Left Column -->
    <div>
        <div class="form-group">
            <label>Activity Information</label>
            <div style="line-height: 1.8;">
                <div><strong>Title:</strong> {{ activity.title }}</div>
                <div><strong>Issuer:</strong> {{ activity.issuer_name or 'N/A' }}</div>
                <div><strong>Duration:</strong> {{ activity.start_date }} to {{ activity.end_date }}</div>
                <div style="margin-top: var(--spacing-md);">
                    <strong>Faculty In-Charge:</strong><br>
                    {% if activity.activity_type and activity.activity_type.faculty_incharge %}
                    {{ activity.activity_type.faculty_incharge.full_name }}
                    {% else %}
                    <span class="text-muted">General / Unassigned</span>
                    {% endif %}
                </div>
            </div>
        </div>

        <div class="form-group mt-4">
            <label>Certificate File</label>
            <div>
                <small class="text-muted d-block mb-2">{{ activity.certificate_file }}</small>
                <a href="{{ url_for('serve_upload', filename=activity.certificate_file) }}" target="_blank" class="btn btn-sm btn-outline-primary">
                    📄 View Certificate PDF
                </a>
            </div>
        </div>

        <div class="form-group mt-4">
            <label>System Decision</label>
            <div class="alert alert-warning" style="margin-bottom: 0;">
                <strong>Auto-Analysis Result:</strong> {{ activity.auto_decision }}
            </div>
        </div>
    </div>

    <!-- Right Column -->
    <div>
        <label>Detected Links & IDs</label>
        <p class="text-muted">Extracted from certificate analysis:</p>
        <div style="max-height: 300px; overflow-y: auto; background: var(--border-light); padding: var(--spacing-md); border: 1px solid var(--border-color); border-radius: 0.375rem; font-family: monospace; font-size: 0.85rem;">
            <div><strong>URLs Found:</strong></div>
            <div style="word-break: break-all; color: var(--text-gray); margin-bottom: var(--spacing-md);">{{ activity.urls_json }}</div>
            <div><strong>IDs Found:</strong></div>
            <div style="word-break: break-all; color: var(--text-gray);">{{ activity.ids_json }}</div>
        </div>
    </div>
</div>
```

#### Approval & Rejection Forms (Side-by-Side)
```html
<div class="card">
    <div class="card-header">
        <strong>Your Decision</strong>
    </div>
    <div class="card-body">
        <div class="grid-2">
            <!-- Approve Form -->
            <form action="{{ url_for('approve_request', act_id=activity.id) }}" method="post">
                <div class="form-group">
                    <label for="faculty_comment_approve">
                        <strong>Approval Comments</strong>
                        <small class="text-muted">(Optional)</small>
                    </label>
                    <textarea 
                        name="faculty_comment" 
                        id="faculty_comment_approve" 
                        class="form-control" 
                        rows="4" 
                        placeholder="Add any notes about this approval...">
                    </textarea>
                </div>
                <button type="submit" class="btn btn-success w-100" style="padding: var(--spacing-md); font-weight: 600;">
                    ✓ Approve (Genuine Certificate)
                </button>
            </form>

            <!-- Reject Form -->
            <form action="{{ url_for('reject_request', act_id=activity.id) }}" method="post">
                <div class="form-group">
                    <label for="faculty_comment_reject">
                        <strong>Rejection Reason</strong>
                        <small class="text-muted">(Optional)</small>
                    </label>
                    <textarea 
                        name="faculty_comment" 
                        id="faculty_comment_reject" 
                        class="form-control" 
                        rows="4" 
                        placeholder="Please explain why you're rejecting this certificate...">
                    </textarea>
                </div>
                <button type="submit" class="btn btn-danger w-100" style="padding: var(--spacing-md); font-weight: 600;">
                    ✗ Reject (Suspicious/Invalid)
                </button>
            </form>
        </div>
    </div>
</div>
```

### Jinja2 Variables Used
- `activity` - Single StudentActivity object with all details
- `activity.id`, `.title`, `.issuer_name`, `.start_date`, `.end_date`
- `activity.student.full_name`, `.institution_id`
- `activity.activity_type.faculty_incharge.full_name`
- `activity.certificate_file`, `.auto_decision`, `.urls_json`, `.ids_json`
- `current_user` info (same as queue)
- `url_for()` for approve/reject/upload routes

---

## File 3: CSS Styling (`static/style_faculty_queue.css`)

### Queue Table Styles
```css
.table-responsive {
    border-radius: 0.375rem;
    overflow: hidden;
    box-shadow: var(--shadow-sm);
}

.queue-table {
    width: 100%;
    border-collapse: collapse;
    background-color: var(--white);
}

.queue-table thead {
    background-color: var(--border-light);
    border-bottom: 2px solid var(--border-color);
}

.queue-table th {
    padding: var(--spacing-md) var(--spacing-lg);
    text-align: left;
    font-weight: 600;
    font-size: 0.95rem;
    color: var(--text-dark);
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* Zebra striping */
.queue-table tbody tr:nth-child(odd) {
    background-color: #fafbfc;
}

.queue-table tbody tr:nth-child(even) {
    background-color: var(--white);
}

.queue-table tbody tr:hover {
    background-color: #f0f4f8;
}

.queue-table td {
    padding: var(--spacing-md) var(--spacing-lg);
    font-size: 0.95rem;
    color: var(--text-dark);
    vertical-align: middle;
}
```

### Column-Specific Styles
```css
/* Roll number in code format */
.queue-table td code {
    background-color: var(--border-light);
    padding: 0.25rem 0.5rem;
    border-radius: 0.25rem;
    font-family: monospace;
    font-size: 0.85rem;
    color: var(--primary-color);
}

/* Activity title */
.activity-title {
    font-weight: 500;
    margin-bottom: 0.375rem;
}

/* Small badges for categories */
.badge-small {
    display: inline-block;
    padding: 0.25rem 0.5rem;
    font-size: 0.8rem;
    font-weight: 600;
    border-radius: 0.25rem;
    text-transform: uppercase;
    letter-spacing: 0.3px;
}

.badge-small.bg-secondary {
    background-color: var(--text-gray);
    color: var(--white);
}

/* Date formatting */
.date-cell {
    white-space: nowrap;
    color: var(--text-gray);
    font-size: 0.9rem;
}

/* Status badges with color coding */
.status-badge {
    display: inline-block;
    padding: 0.375rem 0.75rem;
    border-radius: 0.375rem;
    font-size: 0.85rem;
    font-weight: 600;
    text-align: center;
}

.status-pending {
    background-color: #fef3c7;    /* Light yellow */
    color: #92400e;                 /* Dark brown text */
}

.status-flagged {
    background-color: #fee2e2;    /* Light red */
    color: #991b1b;                 /* Dark red text */
}

.status-auto-verified {
    background-color: #dcfce7;    /* Light green */
    color: #166534;                 /* Dark green text */
}

/* Action column width */
.action-col {
    width: 130px;
    text-align: center;
}

.queue-table .btn-sm {
    padding: 0.375rem 0.75rem;
    font-size: 0.85rem;
    white-space: nowrap;
}
```

### Responsive Design
```css
/* Tablet (991px and below) */
@media (max-width: 991px) {
    .queue-table th,
    .queue-table td {
        padding: var(--spacing-sm) var(--spacing-md);
    }

    .activity-title {
        font-size: 0.9rem;
    }
}

/* Mobile (768px and below) */
@media (max-width: 768px) {
    .queue-table {
        font-size: 0.85rem;
    }

    .queue-table th,
    .queue-table td {
        padding: var(--spacing-sm) var(--spacing-md);
    }

    .activity-title {
        font-size: 0.9rem;
        margin-bottom: 0.25rem;
    }

    .date-cell {
        font-size: 0.8rem;
    }

    .action-col {
        width: auto;
    }

    .queue-table .btn-sm {
        padding: 0.3rem 0.6rem;
        font-size: 0.75rem;
    }
    
    /* Stack approval/rejection forms vertically */
    .grid-2 {
        grid-template-columns: 1fr;
    }
}

/* Small screens (576px and below) */
@media (max-width: 576px) {
    /* Hide "Uploaded Date" column to save space */
    .queue-table th:nth-child(4),
    .queue-table td:nth-child(4) {
        display: none;
    }
}
```

### Grid Layout for Forms
```css
.grid-2 {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: var(--spacing-lg);
}

@media (max-width: 768px) {
    .grid-2 {
        grid-template-columns: 1fr;
    }
}
```

### Badge Colors
```css
.bg-secondary {
    background-color: #6b7280;
    color: var(--white);
}

.bg-warning {
    background-color: #f59e0b;
    color: var(--white);
}

.bg-success {
    background-color: #10b981;
    color: var(--white);
}

.bg-danger {
    background-color: #ef4444;
    color: var(--white);
}
```

---

## Summary of Changes

### Template Changes
| File | Change | Purpose |
|------|--------|---------|
| `faculty_queue.html` | NEW | Display queue table of all pending certificates |
| `faculty_review.html` | NEW | Show full certificate details with approval/rejection |
| `faculty.html` | REPLACED | Old inline template no longer used |

### CSS Changes
| File | Change | Purpose |
|------|--------|---------|
| `style_faculty_queue.css` | NEW | Queue table styling + responsive design |
| `style.css` | UNCHANGED | No modifications needed |

### Route Changes (Python)
| Route | Change | Purpose |
|-------|--------|---------|
| `/faculty` | UPDATED | Now uses `faculty_queue.html` instead of `faculty.html` |
| `/faculty/review/<act_id>` | NEW | Display certificate detail page |
| `/faculty/approve/<act_id>` | UNCHANGED | POST endpoint (same behavior) |
| `/faculty/reject/<act_id>` | UNCHANGED | POST endpoint (same behavior) |

### Data/Variables
- ✅ All Jinja2 variables unchanged
- ✅ No new database queries added
- ✅ Form submission data unchanged (same textarea name)
- ✅ No Python logic changes
