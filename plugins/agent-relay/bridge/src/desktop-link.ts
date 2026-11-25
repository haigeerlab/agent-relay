export interface DesktopLink {
  link: string;
  title?: string;
}

const DESKTOP_LINK = /^claude:\/\/claude\.ai\/epitaxy\/local_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/** paused-session-link D287: validate the desktop app session link and normalize its display title. */
export function desktopLink(input: { link: string; title?: string }): DesktopLink {
  if (!DESKTOP_LINK.test(input.link)) throw new Error("desktop link must be a Claude desktop session link.");
  const title = input.title?.replace(/[\x00-\x1F\x7F-\x9F]/g, "").replace(/\s+/g, " ").trim();
  const truncated = title && Array.from(title).slice(0, 120).join("");
  return truncated ? { link: input.link, title: truncated } : { link: input.link };
}

/** paused-session-link D289: name a Claude desktop session for text shown to its sender or user. */
export function desktopSessionName(agent: string, desktop?: DesktopLink | null): string {
  return desktop?.title ? `'${desktop.title}' (mailbox name ${agent})` : agent;
}

/** paused-session-link D291: derive the app's local session id only from a validated stored link. */
export function desktopSessionId(desktop?: DesktopLink | null): string | null {
  return desktop?.link.match(/epitaxy\/(local_[0-9a-f-]{36})$/)?.[1] ?? null;
}

/** paused-session-link D289: the same fact for the user, who reads the notification and opens the session. */
export function pausedSessionUserText(agent: string, desktop?: DesktopLink | null): string {
  return `The Claude app paused this session or it was closed. Open the Claude session ${desktopSessionName(agent, desktop)} to deliver them.`;
}

export function pausedSessionText(agent: string, desktop?: DesktopLink | null, manualWake = false): string {
  const name = desktopSessionName(agent, desktop);
  const shared = `The Claude app paused this session or it was closed; it reads its mailbox only after it is opened. Tell the user: ` +
    `"Open the Claude session ${name} so it can read its waiting messages."`;
  const sessionId = manualWake ? desktopSessionId(desktop) : null;
  return sessionId ? `${shared} If the user asks to wake it now and you are a Claude session in the desktop app, you may send it one line with the app's session message tool to session ${sessionId}, asking it to read its mailbox. Do not do this unasked or repeatedly; the app may pause another session to make room.` : shared;
}

