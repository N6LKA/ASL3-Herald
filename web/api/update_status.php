<?php
require __DIR__ . '/../herald-common.php';

// Read-only - no sudo (same reasoning as list.php). Polled every few
// seconds while an update is in progress, and once on page load to resume
// showing progress if one was already running when the page opened.
$result = herald_run(['update-status']);
$data = json_decode($result['stdout'], true);

if (!is_array($data)) {
    herald_json_response(['success' => false, 'message' => 'Could not read update status'], 500);
}

herald_json_response($data);
