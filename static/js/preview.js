// Speed Camera Preview Page JavaScript - On-Demand Refresh

function updatePreview() {
    const timestamp = new Date().getTime();
    const img = document.getElementById('preview-image');
    img.src = `/api/preview?t=${timestamp}`;
    document.getElementById('preview-timestamp').textContent =
        new Date().toLocaleTimeString();
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Load preview immediately
    updatePreview();

    // Set up refresh button
    document.getElementById('refresh-btn').addEventListener('click', updatePreview);
});
