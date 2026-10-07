// agent-relay ops-commands (D43): read a message body from a file so it arrives byte-identical, with no shell quoting.
import { closeSync, constants, fstatSync, lstatSync, openSync, readSync } from "node:fs";
import { isAbsolute } from "node:path";

export const MAX_BODY_FILE_BYTES = 256 * 1024;

export class BodyFileError extends Error {}

/**
 * The text of `path`: an absolute path to a regular file (not a symbolic link) owned by this user, 1 byte to 256 KiB,
 * valid UTF-8. The file is opened without following links and must still be the file that was checked.
 */
export function readBodyFile(path: string): string {
  if (!isAbsolute(path)) throw new BodyFileError(`bodyFile must be an absolute path, not "${path}".`);
  let checked;
  try {
    checked = lstatSync(path);
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") throw new BodyFileError(`bodyFile ${path} does not exist.`);
    throw new BodyFileError(`bodyFile ${path} cannot be read: ${(error as Error).message}`);
  }
  if (checked.isSymbolicLink()) throw new BodyFileError(`bodyFile ${path} is a symbolic link; pass the file itself.`);
  if (!checked.isFile()) throw new BodyFileError(`bodyFile ${path} is not a regular file.`);
  if (process.getuid && checked.uid !== process.getuid()) throw new BodyFileError(`bodyFile ${path} is not owned by this user.`);
  if (checked.size === 0) throw new BodyFileError(`bodyFile ${path} is empty.`);
  if (checked.size > MAX_BODY_FILE_BYTES) throw new BodyFileError(`bodyFile ${path} is larger than 256 KiB.`);

  const fd = openSync(path, constants.O_RDONLY | constants.O_NOFOLLOW);
  try {
    const opened = fstatSync(fd);
    if (opened.ino !== checked.ino || opened.dev !== checked.dev || opened.size !== checked.size) {
      throw new BodyFileError(`bodyFile ${path} changed while it was being read; try again.`);
    }
    const bytes = Buffer.alloc(checked.size);
    let read = 0;
    while (read < bytes.length) {
      const n = readSync(fd, bytes, read, bytes.length - read, read);
      if (n === 0) break;
      read += n;
    }
    if (read !== bytes.length) throw new BodyFileError(`bodyFile ${path} changed while it was being read; try again.`);
    try {
      // ignoreBOM keeps a leading byte-order mark, so the stored text re-encodes to the same bytes.
      return new TextDecoder("utf-8", { fatal: true, ignoreBOM: true }).decode(bytes);
    } catch {
      throw new BodyFileError(`bodyFile ${path} is not valid UTF-8 text.`);
    }
  } finally {
    closeSync(fd);
  }
}
