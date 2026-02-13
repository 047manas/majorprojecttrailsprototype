// Dashboard Logic with DataTables, Chart.js, and Advanced Exports

// Global Chart Instances
let charts = {
    dist: null,
    trend: null,
    dept: null,
    verify: null
};

// Global DataTable Instance
let studentTable = null;

// Current filter state (for export URLs)
let currentFilters = new URLSearchParams();

const API = {
    DIST: '/analytics/api/distribution',
    TREND: '/analytics/api/yearly-trend',
    KPIS: '/analytics/api/kpis',
    LIST: '/analytics/api/student-list',
    DEPT: '/analytics/api/department-participation',
    VERIFY: '/analytics/api/verification-summary',
    INSIGHTS: '/analytics/api/insights',
    HEALTH: '/analytics/api/health',
    COMPARE: '/analytics/api/comparison'
};

const EXPORT = {
    NAAC: '/analytics/export-naac',
    TABLE: '/analytics/export-students-table',
    SNAPSHOT: '/analytics/export-snapshot',
    EVENT: '/analytics/export-event-instance'
};

// Set Chart Text Color
if (Chart.defaults) {
    Chart.defaults.color = '#858796';
    Chart.defaults.font.family = "'Inter', system-ui, -apple-system, sans-serif";
}

document.addEventListener('DOMContentLoaded', () => {
    initDashboard();
});

function initDashboard() {
    initDataTable();

    // Reset Filters Button
    window.resetFilters = function () {
        document.getElementById('filterForm').reset();
        reloadDashboard();
    };

    // Compare Toggle Listener
    const toggle = document.getElementById('compareToggle');
    if (toggle) {
        toggle.addEventListener('change', reloadDashboard);
    }

    // Initial Load
    reloadDashboard();

    // Load Global Health (Once)
    loadHealth();
}

function initDataTable() {
    studentTable = $('#studentTable').DataTable({
        responsive: true,
        pageLength: 20,
        dom: 'frtip',
        order: [[4, 'desc']], // Date desc (shifted due to new column)
        columns: [
            { data: 'student_name' },
            { data: 'department' },
            {
                data: 'title',
                render: function (data, type, row) {
                    return `<div><div class="fw-bold text-dark">${data}</div><div class="text-xs text-muted">${row.category || ''}</div></div>`;
                }
            },
            {
                data: 'status',
                render: function (data) {
                    let badgeClass = 'bg-secondary';
                    if (data === 'faculty_verified' || data === 'auto_verified') badgeClass = 'bg-success';
                    else if (data === 'pending') badgeClass = 'bg-warning text-dark';
                    else if (data === 'rejected') badgeClass = 'bg-danger';

                    const statusText = data ? data.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase()) : 'N/A';
                    return `<span class="badge ${badgeClass}">${statusText}</span>`;
                }
            },
            { data: 'date' },
            {
                // Certificate Column
                data: 'certificate_url',
                orderable: false,
                render: function (data, type, row) {
                    if (data) {
                        return `<a href="${data}" target="_blank" class="btn btn-sm btn-outline-primary py-0 px-2"><i class="fas fa-file-alt me-1"></i>View</a>`;
                    }
                    return `<span class="text-muted text-xs">Unavailable</span>`;
                }
            }
        ],
        language: {
            search: "",
            searchPlaceholder: "Search within results...",
            zeroRecords: "No matching records found",
            emptyTable: "No data available in table"
        }
    });

    // Link custom search input to DataTable
    $('#tableSearch').on('keyup', function () {
        studentTable.search(this.value).draw();
    });
}

function reloadDashboard() {
    // Gather Filter Values
    const filters = new URLSearchParams();
    const activeFilters = [];

    // Status
    const status = document.getElementById('statusSelect').value;
    if (status) {
        filters.append('status', status);
        activeFilters.push(`Status: ${status}`);
    }

    // Department
    const dept = document.getElementById('deptSelect').value;
    if (dept) {
        filters.append('department', dept);
        activeFilters.push(`Dept: ${dept}`);
    }

    // Batch
    const batch = document.getElementById('batchInput').value;
    if (batch) {
        filters.append('batch', batch);
        activeFilters.push(`Batch: ${batch}`);
    }

    // Date Range
    const start = document.getElementById('dateFrom').value;
    const end = document.getElementById('dateTo').value;
    if (start) {
        filters.append('start_date', start);
        activeFilters.push(`From: ${start}`);
    }
    if (end) {
        filters.append('end_date', end);
        activeFilters.push(`To: ${end}`);
    }

    // Compare Toggle
    const compareMode = document.getElementById('compareToggle').checked;
    if (compareMode) {
        if (start) {
            const year = new Date(start).getFullYear();
            filters.append('year', year);
        }
        activeFilters.push("VS Prev Year");
    }

    // Save to global state for export functions
    currentFilters = filters;

    // Update Active Filters Banner
    const banner = document.getElementById('activeFiltersBanner');
    const bannerText = document.getElementById('filterText');

    if (activeFilters.length > 0) {
        banner.style.display = 'flex';
        banner.classList.remove('d-none');
        bannerText.textContent = activeFilters.join(' | ');
    } else {
        banner.style.display = 'none';
        banner.classList.add('d-none');
        bannerText.textContent = 'All Data';
    }

    // Update Export URLs (NAAC Full Reports)
    const queryString = filters.toString();

    const setHref = (id, url, type) => {
        const el = document.getElementById(id);
        if (el) {
            el.href = `${url}?type=${type}&${queryString}`;
        }
    };

    setHref('exportFull', EXPORT.NAAC, 'full');
    setHref('exportStudents', EXPORT.NAAC, 'students');
    setHref('exportEvents', EXPORT.NAAC, 'events');

    // Update Advanced Export URLs
    const snapshotEl = document.getElementById('exportSnapshot');
    if (snapshotEl) snapshotEl.href = `${EXPORT.SNAPSHOT}?${queryString}`;

    const tableExportEl = document.getElementById('exportTableBtn');
    if (tableExportEl) tableExportEl.href = `${EXPORT.TABLE}?${queryString}`;

    // Reload Components
    if (compareMode) {
        loadComparison(filters);
    } else {
        loadKPIs(filters);
    }

    loadInsights(filters);
    loadCharts(filters, compareMode);
    loadTableData(filters);
}

async function fetchJSON(url, params) {
    try {
        const response = await fetch(`${url}?${params.toString()}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    } catch (e) {
        console.error("API Error:", url, e);
        return null;
    }
}

async function loadHealth() {
    const data = await fetchJSON(API.HEALTH, new URLSearchParams());
    if (!data) return;

    updateText('healthNullDates', data.null_dates_percent + '%');
    updateText('healthMissingDept', data.missing_dept_percent + '%');
    updateText('healthMissingCat', data.missing_category);
    updateText('healthDuplicates', data.duplicate_entries);
}

async function loadInsights(params) {
    const data = await fetchJSON(API.INSIGHTS, params);
    if (!data) return;

    updateText('insightTopDept', data.top_dept);
    updateText('insightTopDeptVal', data.top_dept_val + '% Engagement');

    updateText('insightTopEvent', data.top_event);
    updateText('insightTopEventVal', data.top_event_val + ' Students');

    updateText('insightVerify', data.verification_efficiency + '%');
    updateText('insightRiskCount', data.risk_events.length);

    // Highlight Risk Card if count > 0
    const riskCard = document.getElementById('cardRisk');
    if (riskCard) {
        if (data.risk_events.length > 0) {
            riskCard.classList.remove('border-0');
            riskCard.classList.add('border', 'border-danger');
        } else {
            riskCard.classList.remove('border', 'border-danger');
            riskCard.classList.add('border-0');
        }
    }
}

async function loadKPIs(params) {
    const data = await fetchJSON(API.KPIS, params);

    // Reset Growth Indicators
    document.querySelectorAll('[id$="Growth"]').forEach(el => el.classList.add('d-none'));

    if (!data) return;

    updateKPI('kpiEvents', data.total_events || 0);
    updateKPI('kpiParticipations', data.total_participations || 0);
    updateKPI('kpiStudents', data.total_students || 0);
    updateKPI('kpiVerified', (data.verified_rate || 0) + '%');
}

async function loadComparison(params) {
    const data = await fetchJSON(API.COMPARE, params);

    if (data && data.status === 'disabled') {
        alert("Please select an Academic Year (e.g., 2024 or 2025) in the filters to enable Comparison Mode.");
        document.getElementById('compareToggle').checked = false;
        reloadDashboard();
        return;
    }

    if (!data) return;

    const showGrowth = (id, obj) => {
        updateKPI(id, obj.current);
        const growthEl = document.getElementById(id + 'Growth');
        if (growthEl && obj.growth_pct !== null) {
            growthEl.textContent = `${obj.growth_pct > 0 ? '+' : ''}${obj.growth_pct}% vs Prev`;
            growthEl.classList.remove('d-none', 'text-danger', 'text-success');
            growthEl.classList.add(obj.growth_pct >= 0 ? 'text-success' : 'text-danger');
        }
    };

    if (data.total_events) showGrowth('kpiEvents', data.total_events);
    if (data.total_participations) showGrowth('kpiParticipations', data.total_participations);
    if (data.verified_rate) showGrowth('kpiVerified', data.verified_rate);
    if (data.total_students) showGrowth('kpiStudents', data.total_students);
}

function updateKPI(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function updateText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

async function loadTableData(params) {
    params.set('per_page', 500);

    try {
        const data = await fetchJSON(API.LIST, params);

        if (studentTable) {
            studentTable.clear();
            if (data && data.students) {
                studentTable.rows.add(data.students);
            }
            studentTable.draw();
        }
    } catch (e) { console.error("Table Error", e); }
}

async function loadCharts(params, compareMode = false) {
    // 1. Activity Breakdown (Clickable for Drilldown)
    try {
        const distData = await fetchJSON(API.DIST, params);
        if (Array.isArray(distData) && distData.length > 0) {
            renderChart('dist', 'eventChart', 'doughnut', {
                labels: distData.map(d => d.category),
                datasets: [{
                    data: distData.map(d => d.count),
                    backgroundColor: ['#4e73df', '#1cc88a', '#36b9cc', '#f6c23e', '#e74a3b', '#858796']
                }]
            }, {
                onClick: (e, elements) => {
                    if (elements && elements.length > 0) {
                        const idx = elements[0].index;
                        const label = distData[idx].category;
                        openDrilldown(label, params);
                    }
                },
                cutout: '60%'
            });
        } else {
            showEmptyState('eventChart');
        }
    } catch (e) { showEmptyState('eventChart'); }

    // 2. Yearly Trend
    try {
        const trendData = await fetchJSON(API.TREND, params);
        if (Array.isArray(trendData) && trendData.length > 0) {
            renderChart('trend', 'trendChart', 'line', {
                labels: trendData.map(d => d.year),
                datasets: [{
                    label: 'Participations',
                    data: trendData.map(d => d.total_participations),
                    borderColor: '#4e73df',
                    tension: 0.3,
                    fill: true,
                    backgroundColor: 'rgba(78, 115, 223, 0.05)'
                }]
            });
        } else {
            showEmptyState('trendChart');
        }
    } catch (e) { showEmptyState('trendChart'); }

    // 3. Dept Engagement
    try {
        const deptData = await fetchJSON(API.DEPT, params);
        if (Array.isArray(deptData) && deptData.length > 0) {
            renderChart('dept', 'deptChart', 'bar', {
                labels: deptData.map(d => d.department),
                datasets: [{
                    label: 'Engagement %',
                    data: deptData.map(d => d.engagement_percent),
                    backgroundColor: '#36b9cc',
                    borderRadius: 4
                }]
            }, {
                indexAxis: 'y',
                scales: { x: { max: 100 } }
            });
        } else {
            showEmptyState('deptChart');
        }
    } catch (e) { showEmptyState('deptChart'); }

    // 4. Verification Status
    try {
        const verifyData = await fetchJSON(API.VERIFY, params);
        if (verifyData && (verifyData.verified > 0 || verifyData.not_verified > 0)) {
            renderChart('verify', 'verifyChart', 'doughnut', {
                labels: ['Verified', 'Not/Pending'],
                datasets: [{
                    data: [verifyData.verified, verifyData.not_verified],
                    backgroundColor: ['#1cc88a', '#e74a3b']
                }]
            }, {
                cutout: '70%',
                rotation: -90,
                circumference: 180
            });
        } else {
            showEmptyState('verifyChart');
        }
    } catch (e) { showEmptyState('verifyChart'); }
}

function showEmptyState(canvasId) {
    const canvas = document.getElementById(canvasId);
    const overlay = document.getElementById(canvasId + '-empty');

    if (canvas) canvas.classList.add('d-none');
    if (overlay) {
        overlay.classList.remove('d-none');
        overlay.style.display = 'flex';
    }
}

function renderChart(key, canvasId, type, data, options = {}) {
    const canvas = document.getElementById(canvasId);
    const overlay = document.getElementById(canvasId + '-empty');

    if (canvas) canvas.classList.remove('d-none');
    if (overlay) overlay.classList.add('d-none');

    const ctx = canvas;
    if (!ctx) return;

    if (charts[key]) {
        charts[key].destroy();
        charts[key] = null;
    }

    charts[key] = new Chart(ctx, {
        type: type,
        data: data,
        options: {
            maintainAspectRatio: false,
            responsive: true,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { boxWidth: 12, padding: 15 }
                }
            },
            layout: {
                padding: 10
            },
            ...options
        }
    });
}

// ============================================================
// CHART DOWNLOAD AS PNG
// ============================================================
function downloadChart(chartKey, filename) {
    const chart = charts[chartKey];
    if (!chart) return;

    const link = document.createElement('a');
    link.href = chart.toBase64Image();
    link.download = (filename || chartKey) + '.png';
    link.click();
}

// ============================================================
// DRILLDOWN LOGIC
// ============================================================
async function openDrilldown(category, baseParams) {
    const modal = new bootstrap.Modal(document.getElementById('drilldownModal'));
    modal.show();

    const content = document.getElementById('drilldownContent');
    const bread = document.getElementById('drilldownBreadcrumb');

    bread.innerHTML = `<li class="breadcrumb-item"><a href="#" onclick="return false;">Overview</a></li><li class="breadcrumb-item active">${category}</li>`;

    content.innerHTML = `
        <div class="text-center py-5">
            <div class="spinner-border text-primary" role="status"></div>
            <p class="mt-2 text-muted">Loading events for ${category}...</p>
        </div>
    `;

    const params = new URLSearchParams(baseParams);
    params.set('category_name', category);
    params.set('per_page', 1000);

    try {
        const data = await fetchJSON(API.LIST, params);
        if (data && data.students && data.students.length > 0) {
            // Group by Title + Date
            const eventMap = {};
            data.students.forEach(s => {
                const key = s.title + '::' + s.date;
                if (!eventMap[key]) eventMap[key] = {
                    title: s.title,
                    date: s.date,
                    count: 0,
                    category: s.category,
                    verified: 0
                };
                eventMap[key].count++;
                if (s.status === 'faculty_verified' || s.status === 'auto_verified') eventMap[key].verified++;
            });

            const events = Object.values(eventMap);

            let html = `
                <table class="table table-hover align-middle">
                    <thead class="bg-light"><tr><th>Event</th><th>Date</th><th>Participants</th><th>Actions</th></tr></thead>
                    <tbody>
            `;

            events.forEach(e => {
                const safeTitle = e.title.replace(/'/g, "\\'").replace(/"/g, "&quot;");
                html += `
                    <tr>
                        <td class="fw-bold text-dark">${e.title}</td>
                        <td>${e.date}</td>
                        <td>${e.count} <span class="text-xs text-muted">(${e.verified} Verified)</span></td>
                        <td>
                            <div class="btn-group btn-group-sm">
                                <button class="btn btn-outline-primary" onclick="drilldownEvent('${safeTitle}', '${e.date}', '${e.category}')">
                                    <i class="fas fa-sitemap me-1"></i>Depts
                                </button>
                                <button class="btn btn-outline-success" onclick="exportEventInstance('${safeTitle}', '${e.date}', '${e.category}')">
                                    <i class="fas fa-download me-1"></i>Export
                                </button>
                            </div>
                        </td>
                    </tr>
                `;
            });
            html += `</tbody></table>`;
            content.innerHTML = html;
        } else {
            content.innerHTML = `<p class="text-center text-muted py-4">No events found.</p>`;
        }
    } catch (e) {
        content.innerHTML = `<p class="text-center text-danger py-4">Error loading data.</p>`;
    }
}

async function drilldownEvent(title, date, category) {
    const content = document.getElementById('drilldownContent');
    const bread = document.getElementById('drilldownBreadcrumb');

    bread.innerHTML += `<li class="breadcrumb-item active">${title}</li>`;
    content.innerHTML = `<div class="text-center py-4"><div class="spinner-border"></div></div>`;

    const params = new URLSearchParams();
    params.set('search', title);

    try {
        const data = await fetchJSON(API.LIST, params);
        if (data && data.students) {
            const deptMap = {};
            data.students.forEach(s => {
                if (!deptMap[s.department]) deptMap[s.department] = 0;
                deptMap[s.department]++;
            });

            let html = `<h6 class="mb-3 fw-bold">${title} <span class="text-muted fw-normal">(${date})</span></h6>`;
            html += `<ul class="list-group">`;
            Object.entries(deptMap).forEach(([d, c]) => {
                html += `
                    <li class="list-group-item d-flex justify-content-between align-items-center">
                        ${d}
                        <span class="badge bg-primary rounded-pill">${c} Students</span>
                    </li>
                 `;
            });
            html += `</ul>`;
            content.innerHTML = html;
        }
    } catch (e) {
        content.innerHTML = "Error loading department breakdown.";
    }
}

// ============================================================
// EVENT INSTANCE EXPORT (from Drilldown)
// ============================================================
function exportEventInstance(title, date, category) {
    // Build the event identity string the same way the backend does.
    // For "defined" events, we'd need the activity_type_id which we don't have client-side.
    // So we use the search-based filtered export as a practical approach.
    const params = new URLSearchParams(currentFilters);
    params.set('search', title);

    const url = `${EXPORT.TABLE}?${params.toString()}`;
    window.open(url, '_blank');
}

// ============================================================
// TABLE EXPORT (Current View)
// ============================================================
function exportCurrentTable() {
    const url = `${EXPORT.TABLE}?${currentFilters.toString()}`;
    window.open(url, '_blank');
}

// ============================================================
// SNAPSHOT EXPORT
// ============================================================
function exportSnapshot() {
    const url = `${EXPORT.SNAPSHOT}?${currentFilters.toString()}`;
    window.open(url, '_blank');
}
