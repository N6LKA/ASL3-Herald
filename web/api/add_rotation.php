<?php
require __DIR__ . '/../herald-common.php';

$name       = $_POST['name'] ?? '';
$mode       = $_POST['mode'] ?? '';
$days       = $_POST['days'] ?? 'daily';
$time_start = trim($_POST['time_start'] ?? '');
$time_end   = trim($_POST['time_end'] ?? '');
$node       = trim($_POST['node'] ?? '');

if (!herald_valid_name($name)) {
    herald_json_response(['success' => false, 'message' => 'Invalid or missing name'], 400);
}
// days: "daily" or comma-separated day names - validated loosely here, the
// daemon's own YAML load treats unrecognized values as never-matching.
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

$gating_args = ['--days', $days];
if ($time_start !== '') { $gating_args[] = '--time-start'; $gating_args[] = $time_start; }
if ($time_end   !== '') { $gating_args[] = '--time-end';   $gating_args[] = $time_end; }
if ($node       !== '') { $gating_args[] = '--node';       $gating_args[] = $node; }

if ($mode === 'tts') {
    $text  = trim($_POST['text'] ?? '');
    $voice = trim($_POST['voice'] ?? '');
    if ($text === '') {
        herald_json_response(['success' => false, 'message' => 'Text is required'], 400);
    }
    $args = array_merge(['add', $text, '--name', $name], $gating_args);
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
    $args = array_merge(['add-file', $converted, '--name', $name], $gating_args);
    $result = herald_run_sudo($args);
    @unlink($converted);
    herald_respond_from_cli($result);

} else {
    herald_json_response(['success' => false, 'message' => 'Invalid mode'], 400);
}
