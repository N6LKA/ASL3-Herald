<?php
require __DIR__ . '/../herald-common.php';

$old_name   = $_POST['old_name'] ?? '';
$name       = $_POST['name'] ?? '';
$mode       = $_POST['mode'] ?? '';
$days       = $_POST['days'] ?? 'daily';
$time_start = trim($_POST['time_start'] ?? '');
$time_end   = trim($_POST['time_end'] ?? '');
$node       = trim($_POST['node'] ?? '');

if (!herald_valid_name($old_name) || !herald_valid_name($name)) {
    herald_json_response(['success' => false, 'message' => 'Invalid or missing name'], 400);
}
if (!preg_match('/^[a-z,]+$/', $days)) {
    herald_json_response(['success' => false, 'message' => 'Invalid days value'], 400);
}
if ($time_start !== '' && !preg_match('/^\d{2}:\d{2}$/', $time_start)) {
    herald_json_response(['success' => false, 'message' => 'Invalid time-start (expected HH:MM)'], 400);
}
if ($time_end !== '' && !preg_match('/^\d{2}:\d{2}$/', $time_end)) {
    herald_json_response(['success' => false, 'message' => 'Invalid time-end (expected HH:MM)'], 400);
}
if ($node !== '' && !preg_match('/^[0-9]+$/', $node)) {
    herald_json_response(['success' => false, 'message' => 'Invalid node number'], 400);
}

// Always passed (even empty) so an edit can explicitly clear a previously-set
// gating field back to "always eligible" - same convention as --week on the
// scheduled-announcement edit endpoint.
$gating_args = ['--days', $days, '--time-start', $time_start, '--time-end', $time_end, '--node', $node];

if ($mode === 'tts') {
    $text  = trim($_POST['text'] ?? '');
    $voice = trim($_POST['voice'] ?? '');
    if ($text === '') {
        herald_json_response(['success' => false, 'message' => 'Text is required'], 400);
    }
    $args = array_merge(['edit-rotation', $old_name, '--new-name', $name, '--text', $text], $gating_args);
    if ($voice !== '') { $args[] = '--voice'; $args[] = $voice; }
    herald_respond_from_cli(herald_run_sudo($args));

} elseif ($mode === 'file') {
    $args = array_merge(['edit-rotation', $old_name, '--new-name', $name], $gating_args);
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
