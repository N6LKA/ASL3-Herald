<?php
require __DIR__ . '/../herald-common.php';

$name = $_POST['name'] ?? '';
$mode = $_POST['mode'] ?? '';

if (!herald_valid_name($name)) {
    herald_json_response(['success' => false, 'message' => 'Invalid or missing name'], 400);
}

if ($mode === 'tts') {
    $text  = trim($_POST['text'] ?? '');
    $voice = trim($_POST['voice'] ?? '');
    if ($text === '') {
        herald_json_response(['success' => false, 'message' => 'Text is required'], 400);
    }
    $args = ['add', $text, '--name', $name];
    if ($voice !== '') {
        $args[] = '--voice';
        $args[] = $voice;
    }
    herald_respond_from_cli(herald_run_sudo($args));

} elseif ($mode === 'file') {
    if (!isset($_FILES['file'])) {
        herald_json_response(['success' => false, 'message' => 'No file uploaded'], 400);
    }
    $converted = herald_handle_upload($_FILES['file']);
    if ($converted === null) {
        herald_json_response(['success' => false, 'message' => 'Upload failed or unsupported format (.wav/.mp3 only)'], 400);
    }
    $result = herald_run_sudo(['add-file', $converted, '--name', $name]);
    @unlink($converted);
    herald_respond_from_cli($result);

} else {
    herald_json_response(['success' => false, 'message' => 'Invalid mode'], 400);
}
