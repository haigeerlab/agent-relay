// agent-relay codex-gated-wake: a test run never shows a desktop notification (tests that check them pass their own env).
process.env.AGENT_RELAY_NOTIFY ??= "off";
