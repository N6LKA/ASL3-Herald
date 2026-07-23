<?php
require __DIR__ . '/../herald-common.php';

$input = json_decode(file_get_contents('php://input'), true) ?? [];

$text = trim($input['text'] ?? '');
if ($text === '' || strlen($text) > 500) {
    herald_json_response(['success' => false, 'message' => 'Text is required (max 500 characters)'], 400);
}

$voice = trim($input['voice'] ?? '');

$args = ['add-timeweather-message', $text];
if ($voice !== '') { $args[] = '--voice'; $args[] = $voice; }

herald_respond_from_cli(herald_run_sudo($args));
