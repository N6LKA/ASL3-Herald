<?php
require __DIR__ . '/../herald-common.php';

// Runs the same check the nightly automatic check uses (see
// perform_update_check() in asl3-herald.py) and records the result in the
// daemon's state file - so clicking this button updates the header badge
// immediately too, not just this tab's message, and there's exactly one
// implementation of the version-compare logic instead of a separate one
// living here in PHP.
herald_respond_from_cli(herald_run_sudo(['check-update']));
