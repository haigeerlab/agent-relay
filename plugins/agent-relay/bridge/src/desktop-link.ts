export interface DesktopLink {
  link: string;
  title?: string;
}

const DESKTOP_LINK = /^claude:\/\/claude\.ai\/epitaxy\/local_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/** paused-session-link D287: validate the desktop app session link and normalize its display title. */
export function desktopLink(input: { link: string; title?: string }): DesktopLink {
  if (!DESKTOP_LINK.test(input.link)) throw new Error("desktop link must be a Claude desktop session link.");
  const title = input.title?.replace(/[\x00-\x1F\x7F-\x9F]/g, "").replace(/\s+/g, " ").trim().slice(0, 120);
  return title ? { link: input.link, title } : { link: input.link };
}

