<?php
require __DIR__ . '/../herald-common.php';

$name = trim($_POST['name'] ?? '');
if (!herald_valid_name($name)) {
    herald_json_response(['success' => false, 'message' => 'Invalid or missing name'], 400);
}

herald_respond_from_cli(herald_run_sudo(['toggle-schedule', $name]));
