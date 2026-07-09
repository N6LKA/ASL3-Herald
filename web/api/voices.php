<?php
require __DIR__ . '/../herald-common.php';

$result = herald_run(['voices', '--json']);
$data = json_decode($result['stdout'], true);

if (!is_array($data) || !isset($data['voices'])) {
    $data = ['voices' => []];
}

herald_json_response($data);
