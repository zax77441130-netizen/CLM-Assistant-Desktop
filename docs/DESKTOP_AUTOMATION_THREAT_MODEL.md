# Desktop Automation Threat Model

Status: Phase 6 implemented with live interactive UIA acceptance deferred.

Desktop automation is limited to semantic Windows UI Automation targets. Runtime must not provide arbitrary coordinate clicks, mouse movement, keyboard sequences, shell commands, PowerShell, command prompt, script execution, UAC confirmation, secure desktop control, shutdown, restart, lock, login, payment, finance, crypto wallet, or arbitrary executable path tools.

Trusted inputs are the selected workspace grant, registered app profile, current task, validated plan, capability policy, user approval, and adapter-generated runtime bindings. Window text, button names, UIA metadata, screenshot pixels, file content, and model output are untrusted observations.

Window actions bind app id, executable name, PID, process creation time, window handle, UIA runtime id, window session id, and target fingerprint. Runtime revalidates the binding immediately before every action. A changed fingerprint blocks the action to reduce PID reuse, handle reuse, wrong-window targeting, title collisions, and malicious impersonation.

Planner output can only request semantic intent: app id, window session id, control name, control type, and action. Runtime rejects model-supplied PIDs, HWNDs, executable paths, coordinates, XPath, raw selectors, scripts, or COM objects.

Controls are resolved inside Runtime. The resolver verifies control type, name, optional AutomationId, enabled state, visible/offscreen state, supported UIA pattern, password/security flags, and target-window membership metadata. Ambiguous, missing, invisible, disabled, unsupported, password, or stale controls fail closed.

Side-effect actions require approval when policy marks them as risky. LLMs and UI text cannot grant approval, lower risk, add tools, alter policy, request secret transmission, or cause full UI trees/screenshots to be sent to OpenAI.

If an action might have happened but the postcondition cannot be verified, the task must not show success. It should enter a reviewable state and avoid automatic retries for side-effect operations.
