/** Client-side logger for Morphic-Agent UI.
 *
 * Wraps console.* with a [Morphic] prefix and log-level filtering.
 * Set LOG_LEVEL via NEXT_PUBLIC_LOG_LEVEL env var (debug|info|warn|error).
 */

type LogLevel = "debug" | "info" | "warn" | "error";

const LEVELS: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

const currentLevel: LogLevel =
  (process.env.NEXT_PUBLIC_LOG_LEVEL as LogLevel) || "info";

function shouldLog(level: LogLevel): boolean {
  return LEVELS[level] >= LEVELS[currentLevel];
}

function timestamp(): string {
  return new Date().toLocaleTimeString("en-US", { hour12: false });
}

export const logger = {
  debug(msg: string, ...args: unknown[]) {
    if (shouldLog("debug")) {
      console.debug(`${timestamp()} | DEBUG | [Morphic] ${msg}`, ...args);
    }
  },

  info(msg: string, ...args: unknown[]) {
    if (shouldLog("info")) {
      console.info(`${timestamp()} | INFO  | [Morphic] ${msg}`, ...args);
    }
  },

  warn(msg: string, ...args: unknown[]) {
    if (shouldLog("warn")) {
      console.warn(`${timestamp()} | WARN  | [Morphic] ${msg}`, ...args);
    }
  },

  error(msg: string, ...args: unknown[]) {
    if (shouldLog("error")) {
      console.error(`${timestamp()} | ERROR | [Morphic] ${msg}`, ...args);
    }
  },
};
