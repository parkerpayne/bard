/**
 * Where the shell remembers which bot to talk to.
 *
 * Only the server address lives here — the hotkey bindings themselves are the
 * server's, so signing in on another machine brings them with it.
 */
import { app } from 'electron';
import { readFileSync, writeFileSync } from 'node:fs';
import path from 'node:path';

export interface Config {
  serverUrl: string | null;
}

const EMPTY: Config = { serverUrl: null };

function file(): string {
  return path.join(app.getPath('userData'), 'config.json');
}

/** Normalise to a bare origin: the shell only ever loads "/" and calls "/api". */
export function normaliseServerUrl(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  // A bare "192.168.1.158:5000" is what people actually type.
  // A scheme we do not speak must be rejected, not quietly prefixed: without
  // this "ftp://host" becomes "http://ftp://host", whose host is "ftp".
  const scheme = /^([a-z][a-z0-9+.-]*):\/\//i.exec(trimmed);
  if (scheme && !/^https?$/i.test(scheme[1])) return null;
  const withScheme = scheme ? trimmed : `http://${trimmed}`;
  let url: URL;
  try {
    url = new URL(withScheme);
  } catch {
    return null;
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return null;
  // URL parsing is lenient enough that "ht!tp://%%%" yields the host "ht!tp".
  // Anything that is not a plausible hostname or IP literal is a typo, and
  // saying so beats loading a window that can never connect.
  const host = url.hostname;
  const isName = /^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$/i.test(host);
  const isIpv6 = /^\[[0-9a-f:.]+\]$/i.test(host);
  if (!isName && !isIpv6) return null;
  return url.origin;
}

export function load(): Config {
  try {
    const parsed = JSON.parse(readFileSync(file(), 'utf8')) as Partial<Config>;
    const url = typeof parsed.serverUrl === 'string' ? normaliseServerUrl(parsed.serverUrl) : null;
    return { serverUrl: url };
  } catch {
    // Missing or corrupt: a first run and a mangled file want the same thing.
    return { ...EMPTY };
  }
}

export function save(config: Config): void {
  writeFileSync(file(), JSON.stringify(config, null, 2), 'utf8');
}
