<?php
// herald-frame-allmon3.php
//
// Auth-gated entry point for embedding asl3-herald's web UI inside Allmon3
// (via an iframepost entry in allmon3.ini).
//
// We do not reimplement Allmon3's session/login logic. Instead we ask
// Allmon3 itself whether the current visitor is logged in, by calling its
// own "master/auth/check" API endpoint server-side and forwarding the
// browser's cookies exactly as the browser sent them. This keeps us
// correct even if Allmon3 changes its internal session format later.

function isAllmon3LoggedIn(): bool {
    $scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
    $host   = $_SERVER['HTTP_HOST'] ?? 'localhost';
    $checkUrl = "$scheme://$host/allmon3/master/auth/check";

    $cookieHeader = $_SERVER['HTTP_COOKIE'] ?? '';

    $ch = curl_init($checkUrl);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER     => ["Cookie: $cookieHeader"],
        CURLOPT_TIMEOUT        => 3,
        // This is a loopback call to the same host carrying only the cookie
        // the browser already sent this same server, not a third-party
        // request, so we relax peer verification for a self-signed cert.
        CURLOPT_SSL_VERIFYPEER => false,
        CURLOPT_SSL_VERIFYHOST => false,
    ]);
    $response = curl_exec($ch);
    $curlError = curl_error($ch);
    curl_close($ch);

    if ($response === false) {
        error_log("herald-frame-allmon3.php: auth check curl error: $curlError");
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
