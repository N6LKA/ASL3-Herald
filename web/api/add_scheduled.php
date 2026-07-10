<?php
require __DIR__ . '/../herald-common.php';

$name      = $_POST['name'] ?? '';
$time      = $_POST['time'] ?? '';
$days      = $_POST['days'] ?? 'daily';
$week      = $_POST['week'] ?? '';
$play_mode = $_POST['play_mode'] ?? 'local';
$mode      = $_POST['mode'] ?? '';
$node      = trim($_POST['node'] ?? '');

if (!herald_valid_name($name)) {
    herald_json_response(['success' => false, 'message' => 'Invalid or missing name'], 400);
}
if (!preg_match('/^\d{2}:\d{2}$/', $time)) {
    herald_json_response(['success' => false, 'message' => 'Invalid time (expected HH:MM)'], 400);
}
if ($week !== '' && !in_array($week, ['1', '2', '3', '4', '5'], true)) {
    herald_json_response(['success' => false, 'message' => 'Invalid week (must be 1-5)'], 400);
}
// days: "daily" or comma-separated day names — validated loosely here,
// the daemon's own YAML load treats unrecognized values as never-matching.
if (!preg_match('/^[a-z,]+$/', $days)) {
    herald_json_response(['success' => false, 'message' => 'Invalid days value'], 400);
}
if (!in_array($play_mode, ['local', 'global'], true)) {
    herald_json_response(['success' => false, 'message' => 'Invalid play mode'], 400);
}
if ($node !== '' && !preg_match('/^[0-9]+$/', $node)) {
    herald_json_response(['success' => false, 'message' => 'Invalid node number'], 400);
}

if ($mode === 'tts') {
    $text  = trim($_POST['text'] ?? '');
    $voice = trim($_POST['voice'] ?? '');
    if ($text === '') {
        herald_json_response(['success' => false, 'message' => 'Text is required'], 400);
    }
    $args = ['add-schedule', $text, '--name', $name, '--time', $time, '--days', $days, '--play-mode', $play_mode];
    if ($week !== '') { $args[] = '--week'; $args[] = $week; }
    if ($voice !== '') { $args[] = '--voice'; $args[] = $voice; }
    if ($node !== '') { $args[] = '--node'; $args[] = $node; }
    herald_respond_from_cli(herald_run_sudo($args));

} elseif ($mode === 'file') {
    if (!isset($_FILES['file'])) {
        herald_json_response(['success' => false, 'message' => 'No file uploaded'], 400);
    }
    $converted = herald_handle_upload($_FILES['file']);
    if ($converted === null) {
        herald_json_response(['success' => false, 'message' => 'Upload failed or unsupported format (.wav/.mp3 only)'], 400);
    }
    $args = ['add-schedule-file', $converted, '--name', $name, '--time', $time, '--days', $days, '--play-mode', $play_mode];
    if ($week !== '') { $args[] = '--week'; $args[] = $week; }
    if ($node !== '') { $args[] = '--node'; $args[] = $node; }
    $result = herald_run_sudo($args);
    @unlink($converted);
    herald_respond_from_cli($result);

} else {
    herald_json_response(['success' => false, 'message' => 'Invalid mode'], 400);
}
