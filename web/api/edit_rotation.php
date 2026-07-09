<?php
require __DIR__ . '/../herald-common.php';

$old_name = $_POST['old_name'] ?? '';
$name = $_POST['name'] ?? '';
$mode = $_POST['mode'] ?? '';

if (!herald_valid_name($old_name) || !herald_valid_name($name)) {
    herald_json_response(['success' => false, 'message' => 'Invalid or missing name'], 400);
}

if ($mode === 'tts') {
    $text  = trim($_POST['text'] ?? '');
    $voice = trim($_POST['voice'] ?? '');
    if ($text === '') {
        herald_json_response(['success' => false, 'message' => 'Text is required'], 400);
    }
    $args = ['edit-rotation', $old_name, '--new-name', $name, '--text', $text];
    if ($voice !== '') { $args[] = '--voice'; $args[] = $voice; }
    herald_respond_from_cli(herald_run_sudo($args));

} elseif ($mode === 'file') {
    $args = ['edit-rotation', $old_name, '--new-name', $name];
    $converted = null;
    // A new file is optional here: with no upload, the existing audio is
    // kept and only the name (and thus the underlying filename) changes.
    if (isset($_FILES['file']) && $_FILES['file']['error'] !== UPLOAD_ERR_NO_FILE) {
        $converted = herald_handle_upload($_FILES['file']);
        if ($converted === null) {
            herald_json_response(['success' => false, 'message' => 'Upload failed or unsupported format (.wav/.mp3 only)'], 400);
        }
        $args[] = '--file';
        $args[] = $converted;
    }
    $result = herald_run_sudo($args);
    if ($converted !== null) @unlink($converted);
    herald_respond_from_cli($result);

} else {
    herald_json_response(['success' => false, 'message' => 'Invalid mode'], 400);
}
