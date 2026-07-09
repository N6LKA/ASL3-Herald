<?php
// herald-frame-allmon3.php
//
// Auth-gated standalone page for asl3-herald's web UI, linked from Allmon3's
// sidebar via a menu.ini entry (not embedded as an iframe).
//
// We do not reimplement Allmon3's session/login logic. Instead we ask
// Allmon3 itself whether the current visitor is logged in, by calling its
// own "master/auth/check" API endpoint server-side and forwarding the
// browser's cookies exactly as the browser sent them. This keeps us
// correct even if Allmon3 changes its internal session format later.
//
// The check hits Allmon3's internal HTTP port directly (not the public
// hostname) to avoid round-tripping through any CDN/reverse proxy in front
// of the public domain, which can interfere with server-to-server requests
// that don't look like browser traffic. The port is read from Allmon3's own
// web.ini at runtime rather than assumed, since it's configurable there.

function allmon3HttpPort(): int {
    $webIni = '/etc/allmon3/web.ini';
    if (is_readable($webIni)) {
        $ini = parse_ini_file($webIni, true);
        if (isset($ini['web']['HTTP_PORT'])) {
            return (int) $ini['web']['HTTP_PORT'];
        }
    }
    return 16080; // Allmon3's own default when web.ini/HTTP_PORT isn't set
}

function isAllmon3LoggedIn(): bool {
    $port = allmon3HttpPort();
    $checkUrl = "http://127.0.0.1:{$port}/master/auth/check";

    $cookieHeader = $_SERVER['HTTP_COOKIE'] ?? '';

    $ch = curl_init($checkUrl);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER     => ["Cookie: $cookieHeader"],
        CURLOPT_TIMEOUT        => 3,
    ]);
    $response = curl_exec($ch);
    $curlError = curl_error($ch);
    curl_close($ch);

    if ($response === false) {
        error_log("herald-frame-allmon3.php: auth check curl error ($checkUrl): $curlError");
        return false; // fail closed if Allmon3 can't be reached
    }

    $data = json_decode($response, true);
    return isset($data['SUCCESS']) && $data['SUCCESS'] === 'Logged In';
}

if (!isAllmon3LoggedIn()) {
    http_response_code(403);
    echo "<h2 style='text-align:center; color:red; margin-top:80px;'>Access Denied</h2>";
    echo "<p style='text-align:center;'>You must be logged into Allmon3 to view this page.</p>";
    echo "<p style='text-align:center;'><a href='/allmon3/'>&larr; Go to Allmon3</a></p>";
    exit;
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ASL3 Herald</title>
</head>
<body style="margin:0; padding:16px; background:#f4f4f4;">
<?php include __DIR__ . '/herald-ui.inc'; ?>
</body>
</html>
