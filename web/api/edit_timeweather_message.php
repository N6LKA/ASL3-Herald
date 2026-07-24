<?php
require __DIR__ . '/../herald-common.php';

$input = json_decode(file_get_contents('php://input'), true) ?? [];

$id = trim($input['id'] ?? '');
if (!preg_match('/^[a-f0-9]{6,40}$/', $id)) {
    herald_json_response(['success' => false, 'message' => 'Invalid or missing id'], 400);
}

$args = ['edit-timeweather-message', $id];

if (array_key_exists('text', $input)) {
    $text = trim($input['text'] ?? '');
    if ($text === '' || strlen($text) > 500) {
        herald_json_response(['success' => false, 'message' => 'Text is required (max 500 characters)'], 400);
    }
    $args[] = '--text';
    $args[] = $text;
}

if (array_key_exists('voice', $input)) {
    $args[] = '--voice';
    $args[] = trim($input['voice'] ?? '');
}

// See add_timeweather_message.php - carries the currently-selected Mode
// radio along so it isn't lost on the next reload if unsaved.
if (array_key_exists('mode', $input)) {
    $mode = (string) $input['mode'];
    if (!in_array($mode, ['recordings', 'template'], true)) {
        herald_json_response(['success' => false, 'message' => 'Invalid mode'], 400);
    }
    $args[] = '--mode';
    $args[] = $mode;
}

herald_respond_from_cli(herald_run_sudo($args));
