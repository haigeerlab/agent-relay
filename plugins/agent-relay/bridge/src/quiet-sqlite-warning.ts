// agent-relay script-access D242: a script reads one sentence on stderr. Node 22 prints "SQLite is an experimental
// feature" when node:sqlite loads; drop exactly that warning. Imported first by the CLI, before anything loads SQLite.
const emit = process.emitWarning.bind(process) as (...args: unknown[]) => void;
process.emitWarning = ((warning: unknown, ...rest: unknown[]) => {
  const text = typeof warning === "string" ? warning : warning instanceof Error ? warning.message : "";
  const type = typeof rest[0] === "string" ? rest[0] : (rest[0] as { type?: string } | undefined)?.type
    ?? (warning instanceof Error ? warning.name : undefined);
  if (type === "ExperimentalWarning" && /SQLite/.test(text)) return;
  emit(warning, ...rest);
}) as typeof process.emitWarning;
