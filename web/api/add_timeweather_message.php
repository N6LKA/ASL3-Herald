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

// Carries the currently-selected Mode radio along with the message so it
// isn't lost if the user picked "Custom Templates" but hasn't yet clicked
// the main "Save Changes" button - see herald-ui.js's btn-add-tw-msg handler.
if (array_key_exists('mode', $input)) {
    $mode = (string) $input['mode'];
    if (!in_array($mode, ['recordings', 'template'], true)) {
        herald_json_response(['success' => false, 'message' => 'Invalid mode'], 400);
    }
    $args[] = '--mode';
    $args[] = $mode;
}

herald_respond_from_cli(herald_run_sudo($args));
