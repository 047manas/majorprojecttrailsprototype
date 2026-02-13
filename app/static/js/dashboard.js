// Dashboard Logic with DataTables and Chart.js

// Global Chart Instances
let charts = {
    dist: null,
    trend: null,
    dept: null,
    verify: null
};

// Global DataTable Instance
let studentTable = null;

const API = {
    DIST: '/analytics/api/distribution',
    TREND: '/analytics/api/yearly-trend',
    KPIS: '/analytics/api/kpis',
    LIST: '/analytics/api/student-list',
    DEPT: '/analytics/api/department-participation',
    VERIFY: '/analytics/api/verification-summary'
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
    // Initialize DataTable (No Buttons)
    initDataTable();

    // Reset Filters Button
    window.resetFilters = function () {
        document.getElementById('filterForm').reset();
        reloadDashboard();
    };

    // Initial Load
    reloadDashboard();
}

function initDataTable() {
    studentTable = $('#studentTable').DataTable({
        responsive: true,
        pageLength: 20,
        dom: 'frtip', // No Buttons (B)
        order: [[3, 'desc']], // Date desc
        columns: [
            { data: 'student_name' },
            { data: 'department' },
            {
                data: 'title',
                render: function (data, type, row) {
                    // Show title, maybe add category pill?
                    return `<div><div class="fw-bold text-dark">${data}</div><div class="text-xs text-muted">${row.category || ''}</div></div>`;
                }
            },
            { data: 'date' },
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

    // Update Active Filters Banner
    const banner = document.getElementById('activeFiltersBanner');
    const bannerText = document.getElementById('filterText');

    // Check if we have active filters
    if (activeFilters.length > 0) {
        banner.style.display = 'flex';
        banner.classList.remove('d-none');
        bannerText.textContent = activeFilters.join(' | ');
    } else {
        banner.style.display = 'none';
        banner.classList.add('d-none');
        bannerText.textContent = 'All Data';
    }

    // Update Export URLs
    const exportBase = '/analytics/export-naac';
    const queryString = filters.toString();

    // Use & if queryString exists, else nothing (but base url usually needs ?)
    // Our route is /analytics/export-naac?type=...&filters...

    const setHref = (id, type) => {
        const el = document.getElementById(id);
        if (el) {
            el.href = `${exportBase}?type=${type}&${queryString}`;
        }
    };

    setHref('exportFull', 'full');
    setHref('exportStudents', 'students');
    setHref('exportEvents', 'events');

    // Reload Components
    loadKPIs(filters);

    // Clear charts before loading to prevent 'ghosting' or race conditions? 
    // No, renderChart handles destruction.
    loadCharts(filters);

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

async function loadKPIs(params) {
    const data = await fetchJSON(API.KPIS, params);
    if (!data) return;

    updateKPI('kpiEvents', data.total_events || 0);
    updateKPI('kpiParticipations', data.total_participations || 0);
    updateKPI('kpiStudents', data.total_students || 0);
    updateKPI('kpiVerified', (data.verified_rate || 0) + '%');
}

function updateKPI(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

async function loadTableData(params) {
    params.set('per_page', 500); // Fetch reasonable max for client side table

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

async function loadCharts(params) {
    // 1. Activity Breakdown
    try {
        const distData = await fetchJSON(API.DIST, params);
        if (Array.isArray(distData) && distData.length > 0) {
            renderChart('dist', 'eventChart', 'doughnut', {
                labels: distData.map(d => d.category),
                datasets: [{
                    data: distData.map(d => d.count),
                    backgroundColor: ['#4e73df', '#1cc88a', '#36b9cc', '#f6c23e', '#e74a3b', '#858796']
                }]
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
                cutout: '70%'
            });
        } else {
            showEmptyState('verifyChart');
        }
    } catch (e) { showEmptyState('verifyChart'); }
}

function showEmptyState(canvasId) {
    const canvas = document.getElementById(canvasId);
    const overlay = document.getElementById(canvasId + '-empty');

    // Hide Canvas, Show Overlay
    if (canvas) canvas.classList.add('d-none');
    if (overlay) {
        overlay.classList.remove('d-none');
        overlay.style.display = 'flex'; // Ensure flex
    }
}

function renderChart(key, canvasId, type, data, options = {}) {
    // Reset Visibility (Show Canvas, Hide Overlay)
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
