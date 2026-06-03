/**
 * Generates an ISO 8601 timestamp string.
 */
const timestamp = (): string => new Date().toISOString();

/**
 * Core logging function that outputs formatted messages to the console.
 *
 * @param level The log level (INFO, ERROR, DEBUG, WARN).
 * @param message The message to log.
 * @param args Additional arguments to include in the log output.
 */
function logWithLevel(level: 'INFO' | 'ERROR' | 'DEBUG' | 'WARN', message: string, ...args: unknown[]): void {
  const line = `[${level}] ${timestamp()} - ${message}`;
  if (level === 'ERROR') {
    console.error(line, ...args);
    return;
  }

  console.log(line, ...args);
}

/**
 * Simple structured logger for wot_runtime.
 * Provides info, warn, error, and debug methods.
 */
const log = {
  info: (message: string, ...args: unknown[]) => logWithLevel('INFO', message, ...args),
  warn: (message: string, ...args: unknown[]) => logWithLevel('WARN', message, ...args),
  error: (message: string, ...args: unknown[]) => logWithLevel('ERROR', message, ...args),
  debug: (message: string, ...args: unknown[]) => logWithLevel('DEBUG', message, ...args),
};

export default log;
