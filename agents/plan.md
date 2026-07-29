---
mode: primary
description: Plan mode. Disallows all edit tools.
permission:
  doom_loop: ask
  external_directory:
    "*": ask
    /home/kostaz/.local/share/opencode/tool-output/*: allow
    /home/kostaz/.local/share/opencode/plans/*: allow
    /home/kostaz/projects/*: allow
    /home/kostaz/.kilocode/*: allow
  plan_enter: deny
  read:
    "*.env": ask
    "*.env.*": ask
    "*.env.example": allow
  edit:
    "*": deny
    .opencode/plans/*.md: allow
    ../../../../.local/share/opencode/plans/*.md: allow
---
