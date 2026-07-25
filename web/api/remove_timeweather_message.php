<?php
require __DIR__ . '/../herald-common.php';

$input = json_decode(file_get_contents('php://input'), true) ?? [];
$id = trim($input['id'] ?? '');
if (!preg_match('/^[a-f0-9]{6,40}$/', $id)) {
    herald_json_response(['success' => false, 'message' => 'Invalid or missing id'], 400);
}

herald_respond_from_cli(herald_run_sudo(['remove-timeweather-message', $id]));
