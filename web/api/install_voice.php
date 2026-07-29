<?php
require __DIR__ . '/../herald-common.php';

$input = json_decode(file_get_contents('php://input'), true) ?? [];

$voiceId = trim($input['voice_id'] ?? '');
if ($voiceId === '' || !preg_match('/^[a-zA-Z0-9_-]{1,80}$/', $voiceId)) {
    herald_json_response(['success' => false, 'message' => 'Invalid voice ID'], 400);
}

herald_respond_from_cli(herald_run_sudo(['install-voice', $voiceId]));
