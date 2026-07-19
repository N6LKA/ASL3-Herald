<?php
require __DIR__ . '/../herald-common.php';

if ($_SERVER['REQUEST_METHOD'] === 'GET') {
    $result = herald_run(['list-json']);
    $data = json_decode(trim($result['stdout']), true);
    if ($data === null || !isset($data['timeweather'])) {
        herald_json_response(['success' => false, 'message' => 'Could not read Time & Weather settings'], 500);
    }
    herald_json_response(['success' => true, 'timeweather' => $data['timeweather']]);
}

$input = json_decode(file_get_contents('php://input'), true) ?? [];

$enable = ($input['enable'] ?? false) ? 'true' : 'false';

$timeFormat = (string) ($input['time_format'] ?? '12');
if (!in_array($timeFormat, ['12', '24'], true)) {
    herald_json_response(['success' => false, 'message' => 'Invalid time format'], 400);
}

$cron = trim($input['cron'] ?? '0 * * * *');
if (!preg_match('/^[\d\*\/,\-]+ [\d\*\/,\-]+ [\d\*\/,\-]+ [\d\*\/,\-]+ [\d\*\/,\-]+$/', $cron)) {
    herald_json_response(['success' => false, 'message' => 'Invalid cron expression (expected 5 fields: MIN HOUR DOM MON DOW)'], 400);
}

$weatherEnable = ($input['weather_enable'] ?? false) ? 'true' : 'false';

$provider = (string) ($input['provider'] ?? 'auto');
if (!in_array($provider, ['auto', 'metar', 'openmeteo', 'tempest', 'skywarnplus'], true)) {
    herald_json_response(['success' => false, 'message' => 'Invalid weather provider'], 400);
}

$location = trim($input['location'] ?? '');
if ($location !== '' && !preg_match('/^[a-zA-Z0-9 ,\'-]{1,60}$/', $location)) {
    herald_json_response(['success' => false, 'message' => 'Invalid location'], 400);
}

$tempUnit = (string) ($input['temp_unit'] ?? 'F');
if (!in_array($tempUnit, ['F', 'C'], true)) {
    herald_json_response(['success' => false, 'message' => 'Invalid temperature unit'], 400);
}

$announceCondition = ($input['announce_condition'] ?? false) ? 'true' : 'false';
$announceFeelsLike = ($input['announce_feels_like'] ?? false) ? 'true' : 'false';
$announceHumidity  = ($input['announce_humidity'] ?? false) ? 'true' : 'false';

$cacheMaxAge = filter_var($input['cache_max_age'] ?? 10, FILTER_VALIDATE_INT);
if ($cacheMaxAge === false || $cacheMaxAge < 1) {
    herald_json_response(['success' => false, 'message' => 'Invalid cache max age'], 400);
}

$tempestToken = trim($input['tempest_token'] ?? '');
if ($tempestToken !== '' && !preg_match('/^[a-zA-Z0-9-]{1,100}$/', $tempestToken)) {
    herald_json_response(['success' => false, 'message' => 'Invalid Tempest token'], 400);
}

$tempestStation = trim($input['tempest_station'] ?? '');
if ($tempestStation !== '' && !preg_match('/^[0-9]{1,20}$/', $tempestStation)) {
    herald_json_response(['success' => false, 'message' => 'Invalid Tempest station ID'], 400);
}

herald_respond_from_cli(herald_run_sudo([
    'update-timeweather',
    '--enable', $enable,
    '--time-format', $timeFormat,
    '--cron', $cron,
    '--weather-enable', $weatherEnable,
    '--provider', $provider,
    '--location', $location,
    '--temp-unit', $tempUnit,
    '--announce-condition', $announceCondition,
    '--announce-feels-like', $announceFeelsLike,
    '--announce-humidity', $announceHumidity,
    '--cache-max-age', (string) $cacheMaxAge,
    '--tempest-token', $tempestToken,
    '--tempest-station', $tempestStation,
]));
