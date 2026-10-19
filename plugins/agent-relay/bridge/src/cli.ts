#!/usr/bin/env node
// agent-relay script-access D242: node:sqlite's experimental warning is emitted while modules load, before any of
// them runs, so the filter is installed here and the CLI itself is loaded only afterwards.
import "./quiet-sqlite-warning.js";

void import("./cli-main.js");
