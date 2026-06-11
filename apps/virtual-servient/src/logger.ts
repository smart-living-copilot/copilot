function log(level: string, message: string, extra?: unknown): void {
  const suffix =
    extra === undefined
      ? ""
      : ` ${typeof extra === "string" ? extra : JSON.stringify(extra)}`;
  console.log(`${new Date().toISOString()} ${level} ${message}${suffix}`);
}

export default {
  debug: (message: string, extra?: unknown) => log("DEBUG", message, extra),
  info: (message: string, extra?: unknown) => log("INFO", message, extra),
  warn: (message: string, extra?: unknown) => log("WARN", message, extra),
  error: (message: string, extra?: unknown) => log("ERROR", message, extra),
};
