# OpenCode smoke test

`run_e2e.py` installs the current checkout into an isolated OpenCode configuration and runs `opencode debug config` from an empty workspace. It verifies four agents and three custom tools.

```bash
python3 tests/e2e_system/run_e2e.py
```

Exit code `2` means the local `opencode` executable is unavailable. This smoke test does not spend provider quota and does not claim a complete semantic model journey.
