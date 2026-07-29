<?php
require __DIR__ . '/../herald-common.php';

$result = herald_run(['catalog-voices']);
$data = herald_extract_json($result['stdout']);

if ($data === null) {
    herald_json_response(['success' => false, 'message' => 'Could not read voice catalog'], 500);
}

herald_json_response($data);
