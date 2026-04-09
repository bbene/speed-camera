// Speed Camera Dashboard JavaScript

let currentPage = 1;
let currentSort = null;
let chartInstances = {};
const COLORS = {
    primary: '#0d6efd',
    success: '#198754',
    danger: '#dc3545',
    warning: '#ffc107',
    info: '#0dcaf0',
    light: '#f8f9fa'
};

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    initializeDatePickers();
    loadStats();
    loadDetections();
    setupEventListeners();
});

function initializeDatePickers() {
    const today = new Date();
    const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);

    document.getElementById('date-to').valueAsDate = today;
    document.getElementById('date-from').valueAsDate = weekAgo;
}

function getDateRange() {
    const dateFrom = document.getElementById('date-from').value;
    const dateTo = document.getElementById('date-to').value;

    let toDate = null;
    if (dateTo) {
        const date = new Date(dateTo);
        // Set to end of day (23:59:59.999) to include all events on the selected date
        date.setHours(23, 59, 59, 999);
        toDate = date.toISOString();
    }

    return {
        from: dateFrom ? new Date(dateFrom).toISOString() : null,
        to: toDate
    };
}

function loadStats() {
    const { from, to } = getDateRange();
    const params = new URLSearchParams();
    if (from) params.append('from', from);
    if (to) params.append('to', to);

    fetch(`/api/stats?${params}`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.error('Error:', data.error);
                return;
            }

            // Update KPI cards
            document.getElementById('total-vehicles').textContent = data.total;
            document.getElementById('avg-speed-ltr').textContent = data.l2r_avg.toFixed(1) + ' mph';
            document.getElementById('avg-speed-rtl').textContent = data.r2l_avg.toFixed(1) + ' mph';

            // Update charts
            updateSpeedDistributionChart(data.distribution);
            updateDirectionChart(data.distribution);
            updatePeakHoursChart(data.peak_hours);
        })
        .catch(error => console.error('Error loading stats:', error));
}

function loadDetections() {
    const { from, to } = getDateRange();
    const speedMin = parseFloat(document.getElementById('speed-min').value) || 0;
    const speedMax = parseFloat(document.getElementById('speed-max').value) || 200;
    const direction = document.getElementById('direction-filter').value;

    const params = new URLSearchParams({
        page: currentPage,
        per_page: 25,
        speed_min: speedMin,
        speed_max: speedMax
    });

    if (from) params.append('from', from);
    if (to) params.append('to', to);
    if (direction) params.append('direction', direction);

    fetch(`/api/detections?${params}`)
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.error('Error:', data.error);
                return;
            }

            renderDetectionsTable(data.detections);
            renderPagination(data.total, data.per_page);
        })
        .catch(error => console.error('Error loading detections:', error));
}

function renderDetectionsTable(detections) {
    const tbody = document.getElementById('detections-tbody');

    if (detections.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-muted">No detections found</td></tr>';
        return;
    }

    tbody.innerHTML = detections.map(d => {
        const date = new Date(d.timestamp);
        const timeStr = date.toLocaleString();
        const directionLabel = d.direction === 'LTR' ? '→' : '←';
        const directionClass = d.direction === 'LTR' ? 'status-ltr' : 'status-rtl';

        let gifCell = '<td>-</td>';
        if (d.has_gif) {
            gifCell = `<td><img src="/api/gif/${d.id}" class="gif-thumbnail" onclick="showGifModal('/api/gif/${d.id}')" alt="GIF"></td>`;
        }

        return `
            <tr>
                <td>${timeStr}</td>
                <td class="fw-bold">${d.speed_mph}</td>
                <td class="${directionClass}">${directionLabel}</td>
                <td>${d.confidence || '-'}</td>
                <td>${d.area || '-'}</td>
                <td>${d.frames || '-'}</td>
                ${gifCell}
            </tr>
        `;
    }).join('');
}

function renderPagination(total, perPage) {
    const totalPages = Math.ceil(total / perPage);
    const ul = document.getElementById('pagination-ul');

    if (totalPages <= 1) {
        ul.innerHTML = '';
        return;
    }

    let html = '';

    // Previous button
    if (currentPage > 1) {
        html += `<li class="page-item"><a class="page-link" href="#" onclick="goToPage(${currentPage - 1})">Previous</a></li>`;
    }

    // Page numbers
    const startPage = Math.max(1, currentPage - 2);
    const endPage = Math.min(totalPages, currentPage + 2);

    if (startPage > 1) {
        html += `<li class="page-item"><a class="page-link" href="#" onclick="goToPage(1)">1</a></li>`;
        if (startPage > 2) {
            html += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }
    }

    for (let i = startPage; i <= endPage; i++) {
        const active = i === currentPage ? 'active' : '';
        html += `<li class="page-item ${active}"><a class="page-link" href="#" onclick="goToPage(${i})">${i}</a></li>`;
    }

    if (endPage < totalPages) {
        if (endPage < totalPages - 1) {
            html += `<li class="page-item disabled"><span class="page-link">...</span></li>`;
        }
        html += `<li class="page-item"><a class="page-link" href="#" onclick="goToPage(${totalPages})">${totalPages}</a></li>`;
    }

    // Next button
    if (currentPage < totalPages) {
        html += `<li class="page-item"><a class="page-link" href="#" onclick="goToPage(${currentPage + 1})">Next</a></li>`;
    }

    ul.innerHTML = html;
}

function goToPage(page) {
    currentPage = page;
    loadDetections();
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function updateSpeedDistributionChart(distribution) {
    const ctx = document.getElementById('speed-distribution-chart');

    const labels = Object.keys(distribution).sort((a, b) => {
        const aVal = parseInt(a.split('-')[0]);
        const bVal = parseInt(b.split('-')[0]);
        return aVal - bVal;
    });
    const data = labels.map(label => distribution[label]);

    if (chartInstances.speedDistribution) {
        chartInstances.speedDistribution.destroy();
    }

    chartInstances.speedDistribution = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Number of Vehicles',
                data: data,
                backgroundColor: COLORS.primary,
                borderColor: COLORS.primary,
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1
                    }
                }
            }
        }
    });
}

function updateDirectionChart(distribution) {
    const ctx = document.getElementById('direction-chart');

    // Count L2R vs R2L from detections
    // For now, we'll estimate from the speed distribution
    let ltrCount = 0, rtlCount = 0;

    // This is simplified - in a real scenario, you'd calculate from actual data
    // For now, we'll get this from the actual detections

    const params = new URLSearchParams({
        page: 1,
        per_page: 1000
    });

    fetch(`/api/detections?${params}`)
        .then(response => response.json())
        .then(data => {
            ltrCount = data.detections.filter(d => d.direction === 'LTR').length;
            rtlCount = data.detections.filter(d => d.direction === 'RTL').length;

            if (chartInstances.direction) {
                chartInstances.direction.destroy();
            }

            chartInstances.direction = new Chart(ctx, {
                type: 'doughnut',
                data: {
                    labels: ['Left → Right', 'Right → Left'],
                    datasets: [{
                        data: [ltrCount, rtlCount],
                        backgroundColor: [COLORS.info, COLORS.success],
                        borderColor: ['white', 'white'],
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: true,
                    plugins: {
                        legend: {
                            position: 'bottom'
                        }
                    }
                }
            });
        });
}

function updatePeakHoursChart(peakHours) {
    const ctx = document.getElementById('peak-hours-chart');

    const labels = Object.keys(peakHours).map(h => `${h}:00`);
    const data = Object.values(peakHours);

    if (chartInstances.peakHours) {
        chartInstances.peakHours.destroy();
    }

    chartInstances.peakHours = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Detections per Hour',
                data: data,
                borderColor: COLORS.warning,
                backgroundColor: 'rgba(255, 193, 7, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.4,
                pointRadius: 4,
                pointBackgroundColor: COLORS.warning,
                pointBorderColor: 'white',
                pointBorderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        usePointStyle: true
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        stepSize: 1
                    }
                }
            }
        }
    });
}

function showGifModal(gifUrl) {
    const modal = new bootstrap.Modal(document.getElementById('gifModal'));
    document.getElementById('gif-image').src = gifUrl;
    modal.show();
}

function setupEventListeners() {
    document.getElementById('update-btn').addEventListener('click', () => {
        currentPage = 1;
        loadStats();
        loadDetections();
    });

    document.getElementById('filter-btn').addEventListener('click', () => {
        currentPage = 1;
        loadDetections();
    });

    // Sort links
    document.querySelectorAll('.sort-link').forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            currentSort = link.dataset.sort;
            currentPage = 1;
            loadDetections();
        });
    });

    // Allow Enter key on filter inputs
    ['speed-min', 'speed-max', 'direction-filter'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    document.getElementById('filter-btn').click();
                }
            });
        }
    });
}

// Refresh data every 30 seconds
setInterval(() => {
    loadStats();
    loadDetections();
}, 30000);
