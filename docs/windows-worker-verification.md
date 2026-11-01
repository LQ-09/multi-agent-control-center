# Windows worker startup verification

Use Windows-only routing and read-only execution. Plan provides a brief plan; Execute runs `hostname` and `(Get-Process -Id $PID).SessionId`; Review checks actual output and exit codes. A nonzero session confirms interactive execution. The Reviewer decides acceptance; fixable review failures return to Execute.

Disk capacity queries are not part of worker startup acceptance. Do not include WMI/CIM or disk inventory checks in this smoke test.

The result parser retains a complete blocked/failed JSON result when only its closing wrapper is missing. The regression test covers the observed failure and preserved evidence. This source fix has not yet been deployed to Windows.

## Automatic review

Reviewer success completes the task. A fixable review failure with specific feedback returns to Execute in the same workspace, preserving prior artifacts and the completed Plan. Three revision rounds are allowed; external blockers and exhausted revisions stop for user input. Legacy Verifying tasks can be sent back to Review through the new interface. Desktop and remote backend must both be updated; this checkout has not been deployed.

Validation: 107 Python tests, JSON bridge simulated-agent smoke, TypeScript build and bilingual display checks. The new revision loop has not been tested against live model CLIs on Windows.
