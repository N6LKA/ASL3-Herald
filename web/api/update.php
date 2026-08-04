<?php
require __DIR__ . '/../herald-common.php';

// Starts a one-click update (always from main - see UPDATE_INSTALL_CMD's
// comment in asl3-herald.py). This call returns almost instantly: `herald
// update` itself only checks whether one's already running and, if not,
// launches the real work as a detached background process before printing
// success - it never waits for the update to actually finish, since that
// can take minutes and must not be tied to this request's (or PHP's)
// execution time limit. The web UI polls update_status.php for progress.
herald_respond_from_cli(herald_run_sudo(['update']));
