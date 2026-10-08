import { readdirSync, rmSync } from "node:fs";
import { join } from "node:path";

import type { BridgeStore } from "./bridge-store.js";
import { ensurePrivateDirectory } from "./fs-safety.js";
import { sweepDeliveryFailures } from "./notices.js";

const DAY_MS = 24 * 3_600_000;
export const DAILY_BACKUPS_KEPT = 7;
const DAILY_BACKUP = /^bridge-daily-\d{4}-\d{2}-\d{2}\.sqlite$/;

/**
 * Keep a rolling week of daily mailbox copies. Exactly one bridge process per
 * day takes the backup. Set BRIDGE_BACKUPS=0 to disable.
 */
export function dailyBackup(store: BridgeStore, now = Date.now(), keep = DAILY_BACKUPS_KEPT): string | null {
  if (!store.backupDir || process.env.BRIDGE_BACKUPS === "0") return null;
  if (!store.claimInterval("last_daily_backup", DAY_MS - 60_000, now)) return null;
  ensurePrivateDirectory(store.backupDir);
  const path = join(store.backupDir, `bridge-daily-${new Date(now).toISOString().slice(0, 10)}.sqlite`);
  rmSync(path, { force: true }); // VACUUM INTO refuses to overwrite.
  store.backupTo(path);
  const daily = readdirSync(store.backupDir).filter((name) => DAILY_BACKUP.test(name)).sort().reverse();
  for (const name of daily.slice(keep)) rmSync(join(store.backupDir, name), { force: true });
  return path;
}

export interface HousekeeperOptions {
  log?: (message: string) => void;
}

/**
 * Background upkeep shared by every bridge process: tell senders about failed
 * pings and take the daily backup.
 */
export class Housekeeper {
  private timer: NodeJS.Timeout | null = null;
  private ticks = 0;
  private busy = false;

  constructor(
    private readonly store: BridgeStore,
    private readonly options: HousekeeperOptions = {},
  ) {}

  start(intervalMs = 5000): void {
    this.timer = setInterval(() => void this.tick(), intervalMs);
    this.timer.unref();
    void this.tick();
  }

  async tick(now = Date.now()): Promise<void> {
    if (this.busy) return;
    this.busy = true;
    try {
      sweepDeliveryFailures(this.store, now);
      if (this.ticks % 120 === 0) {
        const backup = dailyBackup(this.store, now);
        if (backup) this.options.log?.(`daily backup written to ${backup}`);
      }
    } catch (error) {
      this.options.log?.(`housekeeping error: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      this.ticks += 1;
      this.busy = false;
    }
  }

  stop(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }
}
