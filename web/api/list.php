<?php
require __DIR__ . '/../herald-common.php';

$result = herald_run(['list-json']);
$data = json_decode($result['stdout'], true);

if (!is_array($data)) {
    herald_json_response(['success' => false, 'message' => 'Could not read config'], 500);
}

herald_json_response($data);
