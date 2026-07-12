<?php
require __DIR__ . '/../herald-common.php';

$result = herald_run(['export-config']);
$data = json_decode($result['stdout'], true);

if (!is_array($data)) {
    herald_json_response(['success' => false, 'message' => 'Could not read config'], 500);
}

// Not using herald_json_response() here - this endpoint returns the config
// itself as a downloadable file, not the usual {success, message} wrapper.
header('Content-Type: application/json');
header('Content-Disposition: attachment; filename="asl3-herald-config-backup.json"');
echo json_encode($data, JSON_PRETTY_PRINT);
