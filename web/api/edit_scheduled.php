<?php
require __DIR__ . '/../herald-common.php';

$old_name  = $_POST['old_name'] ?? '';
$name      = $_POST['name'] ?? '';
$cron      = trim($_POST['cron'] ?? '');
$play_mode = $_POST['play_mode'] ?? 'local';
$mode      = $_POST['mode'] ?? '';
$node      = trim($_POST['node'] ?? '');

if (!herald_valid_name($old_name) || !herald_valid_name($name)) {
    herald_json_response(['success' => false, 'message' => 'Invalid or missing name'], 400);
}
if (!preg_match('/^[\d\*\/,\-]+ [\d\*\/,\-]+ [\d\*\/,\-]+ [\d\*\/,\-]+ [\d\*\/,\-]+$/', $cron)) {
    herald_json_response(['success' => false, 'message' => 'Invalid cron expression (expected 5 fields: MIN HOUR DOM MON DOW)'], 400);
}
if (!in_array($play_mode, ['local', 'global'], true)) {
    herald_json_response(['success' => false, 'message' => 'Invalid play mode'], 400);
}
if ($node !== '' && !preg_match('/^[0-9]+$/', $node)) {
    herald_json_response(['success' => false, 'message' => 'Invalid node number'], 400);
}

// --node is always passed (even empty) so an edit can explicitly clear a
// previously-set node override back to the default.
$base_args = ['edit-schedule', $old_name, '--new-name', $name, '--cron', $cron, '--play-mode', $play_mode, '--node', $node];

if ($mode === 'tts') {
    $text  = trim($_POST['text'] ?? '');
    $voice = trim($_POST['voice'] ?? '');
    if ($text === '') {
        herald_json_response(['success' => false, 'message' => 'Text is required'], 400);
    }
    $args = array_merge($base_args, ['--text', $text]);
    if ($voice !== '') { $args[] = '--voice'; $args[] = $voice; }
    herald_respond_from_cli(herald_run_sudo($args));

} elseif ($mode === 'file') {
    $args = $base_args;
    $converted = null;
    // A new file is optional: with no upload, the existing audio is kept
    // and only the schedule metadata changes.
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
