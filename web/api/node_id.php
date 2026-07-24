<?php
require __DIR__ . '/../herald-common.php';

if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    $result = herald_run(['list-json']);
    $data = json_decode(trim($result['stdout']), true);
    if ($data === null || !isset($data['node_id'])) {
        herald_json_response(['success' => false, 'message' => 'Could not read Node ID settings'], 500);
    }
    herald_json_response(['success' => true, 'node_id' => $data['node_id']]);
}

$input = json_decode(file_get_contents('php://input'), true) ?? [];

$text = trim($input['text'] ?? '');
if ($text === '' || strlen($text) > 500) {
    herald_json_response(['success' => false, 'message' => 'Text is required (max 500 characters)'], 400);
}

$voice = trim($input['voice'] ?? '');

$args = ['set-node-id', $text];
if ($voice !== '') { $args[] = '--voice'; $args[] = $voice; }

herald_respond_from_cli(herald_run_sudo($args));
