# Human Acceptance Backlog

Status:

`DEFERRED_BY_USER — consolidated human acceptance will be performed after feature completion`

Deferred final GUI checks:

- Desktop starts and exits cleanly on Windows.
- Main Assistant page hides tool ids, raw JSON, SQL, stack traces, IPC details, ports, and tokens.
- User can select the intended workspace.
- Natural language list/read/duplicate/create-folder tasks work in the selected workspace.
- Create-folder side effect is visible in Windows Explorer and can be undone.
- Multi-step create/copy task shows step progress and preserves completed steps.
- Overwrite enters approval and does not change the file before approval.
- Rejected approval leaves the original file unchanged.
- Waiting approval remains visible after app restart.
- Ambiguous requests ask for clarification.
- Task Center list/detail match Assistant page state.
- Cancel stops unstarted work and leaves completed undoable work recoverable.
- OpenAI mode requires an explicit user key and never shows the full key after saving.
- Phase 5 large-file search shows a Chinese count/size summary without raw tool ids.
- Phase 5 batch copy/move/rename shows pre-operation summary, progress, success/skipped/failed counts, undo availability, and collapsed manifest details.
- Phase 5 recovery UI uses "移至助理回收區" and never presents it as permanent deletion.
- Phase 5 recovery restore refuses to overwrite an existing workspace file.
- Phase 5 ZIP extraction conflict options are understandable: skip, rename, or approved overwrite when implemented in a later UI flow.
- Phase 5 open file/folder actions open only workspace paths through default handlers and reject executable/script files.
- Phase 5 clipboard read requires explicit approval and masks secret-like text.
- Phase 5 clipboard write reports character count without echoing sensitive content.
- Phase 5 process termination approval displays stable process identity before acting.
