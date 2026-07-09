<?php
require __DIR__ . '/../herald-common.php';

$old_name  = $_POST['old_name'] ?? '';
$name      = $_POST['name'] ?? '';
$time      = $_POST['time'] ?? '';
$days      = $_POST['days'] ?? 'daily';
$week      = $_POST['week'] ?? '';
$play_mode = $_POST['play_mode'] ?? 'local';
$mode      = $_POST['mode'] ?? '';

if (!herald_valid_name($old_name) || !herald_valid_name($name)) {
    herald_json_response(['success' => false, 'message' => 'Invalid or missing name'], 400);
}
if (!preg_match('/^\d{2}:\d{2}$/', $time)) {
    herald_json_response(['success' => false, 'message' => 'Invalid time (expected HH:MM)'], 400);
}
if ($week !== '' && !in_array($week, ['1', '2', '3', '4', '5'], true)) {
    herald_json_response(['success' => false, 'message' => 'Invalid week (must be 1-5)'], 400);
}
if (!preg_match('/^[a-z,]+$/', $days)) {
    herald_json_response(['success' => false, 'message' => 'Invalid days value'], 400);
}
if (!in_array($play_mode, ['local', 'global'], true)) {
    herald_json_response(['success' => false, 'message' => 'Invalid play mode'], 400);
}

// --week is always passed (even empty) so an edit can explicitly clear a
// previously-set week-of-month back to "every week" - add_scheduled.php
// only omits it when empty because there's nothing to clear on a new entry.
$base_args = ['edit-schedule', $old_name, '--new-name', $name, '--time', $time, '--days', $days, '--play-mode', $play_mode, '--week', $week];

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
    // and only the schedule metadata (time/days/week/play mode/name) changes.
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
