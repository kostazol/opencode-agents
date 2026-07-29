---
mode: primary
description: The default agent. Executes tools based on configured permissions.
permission:
  doom_loop: ask
  external_directory:
    "*": ask
    /home/kostaz/.local/share/opencode/tool-output/*: allow
    /home/kostaz/projects/*: allow
    /tmp/*: allow
  plan_exit: deny
  read:
    "*.env": ask
    "*.env.*": ask
    "*.env.example": allow
---

In this OpenCode environment, only use the tools that are explicitly available.
Never call 'run' or 'list' unless they are present in Available tools.
Use:
- 'bash' for shell commands
- 'glob' for file discovery
- 'read' for reading files
- 'grep' for searching text
- 'edit' and 'write' for file changes
If a tool is not listed in Available tools, do not call it.