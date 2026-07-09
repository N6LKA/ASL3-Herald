<?php
require __DIR__ . '/../herald-common.php';

$input = json_decode(file_get_contents('php://input'), true) ?? [];
$name = $input['name'] ?? '';

if (!herald_valid_name($name)) {
    herald_json_response(['success' => false, 'message' => 'Invalid name'], 400);
}

herald_respond_from_cli(herald_run_sudo(['remove', $name]));
