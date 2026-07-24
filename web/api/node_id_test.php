<?php
require __DIR__ . '/../herald-common.php';

// Unlike Time & Weather's Test button, this doesn't need the request/poll
// indirection through the daemon - test-node-id doesn't read any data other
// programs write to /tmp (no SkywarnPlus-style PrivateTmp concern), so a
// direct synchronous call is fine.
$input = json_decode(file_get_contents('php://input'), true) ?? [];

$text = trim($input['text'] ?? '');
if ($text === '' || strlen($text) > 500) {
    herald_json_response(['success' => false, 'message' => 'Text is required (max 500 characters)'], 400);
}

$voice = trim($input['voice'] ?? '');

$args = ['test-node-id', $text];
if ($voice !== '') { $args[] = '--voice'; $args[] = $voice; }

herald_respond_from_cli(herald_run_sudo($args));
