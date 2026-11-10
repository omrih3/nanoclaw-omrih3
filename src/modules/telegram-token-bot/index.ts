/**
 * Telegram token bot — a standalone bot that is NOT wired to any agent.
 * It only accepts BotFather tokens from an owner, saves them to .env as a new
 * `telegram-<name>` instance, deletes the token message from the chat, and
 * hot-starts the adapter. Enabled by TELEGRAM_TOKEN_BOT_TOKEN in .env (it must
 * be a different bot than any agent-wired one).
 *
 * Usage (owner, private chat): send `<token>` or `<name> <token>`.
 */
import fs from 'fs';
import path from 'path';

import { readEnvFile } from '../../env.js';
import { log } from '../../log.js';
import { onHostStart, onHostShutdown } from '../../host-lifecycle.js';
import { registerChannelAdapter, startChannelAdapter } from '../../channels/channel-registry.js';
import { TELEGRAM_DEFAULTS, telegramInstanceBridgeFactory } from '../../channels/telegram.js';
import { isOwner } from '../permissions/db/user-roles.js';

const TOKEN_RE = /^\d+:[A-Za-z0-9_-]{30,}$/;
const NAME_RE = /^[a-z0-9][a-z0-9-]*$/;

let stopped = false;
let abort: AbortController | null = null;

async function tg<T>(token: string, method: string, body?: object, signal?: AbortSignal): Promise<T | null> {
  try {
    const res = await fetch(`https://api.telegram.org/bot${token}/${method}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body ?? {}),
      signal,
    });
    const data = (await res.json()) as { ok: boolean; result?: T };
    return data.ok ? (data.result ?? null) : null;
  } catch {
    return null;
  }
}

function envPath(): string {
  return path.join(process.cwd(), '.env');
}

function saveInstance(name: string, token: string): void {
  const file = envPath();
  const key = `TELEGRAM_BOT_TOKEN_${name.toUpperCase().replace(/-/g, '_')}`;
  const lines = fs.existsSync(file) ? fs.readFileSync(file, 'utf-8').split('\n') : [];
  const kept = lines.filter((l) => !l.startsWith(`${key}=`) && !l.startsWith('TELEGRAM_INSTANCES='));
  while (kept.length && kept[kept.length - 1] === '') kept.pop();
  const cur = lines.find((l) => l.startsWith('TELEGRAM_INSTANCES='))?.slice('TELEGRAM_INSTANCES='.length) ?? '';
  const names = [...new Set([...cur.split(','), name].map((s) => s.trim()).filter(Boolean))].sort();
  kept.push(`${key}=${token}`, `TELEGRAM_INSTANCES=${names.join(',')}`, '');
  const tmp = `${file}.tmp`;
  fs.writeFileSync(tmp, kept.join('\n'), { mode: 0o600 });
  fs.renameSync(tmp, file);
}

function existingTokens(): string[] {
  try {
    return fs
      .readFileSync(envPath(), 'utf-8')
      .split('\n')
      .filter((l) => /^TELEGRAM_BOT_TOKEN[A-Z0-9_]*=/.test(l))
      .map((l) => l.slice(l.indexOf('=') + 1).trim());
  } catch {
    return [];
  }
}

async function handleText(botToken: string, chatId: number, text: string): Promise<void> {
  const reply = (t: string) => tg(botToken, 'sendMessage', { chat_id: chatId, text: t });
  const parts = text.trim().split(/\s+/);
  const token = parts.find((p) => TOKEN_RE.test(p));
  if (!token) {
    await reply('Send me a BotFather token (or `name token`) and I will connect it. I do nothing else.');
    return;
  }
  const me = await tg<{ username: string }>(token, 'getMe');
  if (!me) {
    await reply('Telegram rejected that token. Nothing saved.');
    return;
  }
  const given = parts.find((p) => p !== token)?.toLowerCase();
  const name =
    given ??
    me.username
      .toLowerCase()
      .replace(/_?bot$/, '')
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '');
  if (!NAME_RE.test(name)) {
    await reply('Invalid instance name (use lowercase letters, digits, dashes). Nothing saved.');
    return;
  }
  const key = `TELEGRAM_BOT_TOKEN_${name.toUpperCase().replace(/-/g, '_')}`;
  const ownKey = readEnvFile([key])[key];
  if (existingTokens().includes(token) && ownKey !== token) {
    await reply('That token is already used by another instance. Nothing saved.');
    return;
  }
  saveInstance(name, token);
  const instance = `telegram-${name}`;
  registerChannelAdapter(instance, { factory: () => telegramInstanceBridgeFactory(name), defaults: TELEGRAM_DEFAULTS });
  let status: string;
  try {
    const r = await startChannelAdapter(instance);
    status = r === 'started' ? 'running now' : r;
  } catch (err) {
    log.error('Token bot: hot-start failed', { instance, err });
    status = 'saved, but failed to start — restart the service';
  }
  await reply(
    `Connected @${me.username} as "${instance}" (${status}).\nNow ask the God agent to wire it to an agent. Delete your token message if it's still visible.`,
  );
}

async function pollLoop(botToken: string, signal: AbortSignal): Promise<void> {
  let offset = 0;
  while (!stopped && !signal.aborted) {
    const updates = await tg<
      Array<{
        update_id: number;
        message?: { message_id: number; text?: string; chat: { id: number; type: string }; from?: { id: number } };
      }>
    >(botToken, 'getUpdates', { offset, timeout: 30, allowed_updates: ['message'] }, signal);
    if (!updates) {
      log.warn('Token bot: getUpdates failed, retrying');
      await new Promise((r) => setTimeout(r, 5000));
      continue;
    }
    for (const u of updates) {
      offset = u.update_id + 1;
      const m = u.message;
      if (!m?.text || m.chat.type !== 'private' || !m.from) {
        log.info('Token bot: ignoring non-text/non-private update', { chatType: m?.chat.type });
        continue;
      }
      let owner = false;
      try {
        owner = await isOwner(`telegram:${m.from.id}`);
      } catch (err) {
        log.error('Token bot: owner check failed', { err });
      }
      if (!owner) {
        log.info('Token bot: ignoring non-owner', { fromId: m.from.id });
        continue; // silently ignore non-owners
      }
      if (
        TOKEN_RE.test(
          m.text
            .trim()
            .split(/\s+/)
            .find((p) => TOKEN_RE.test(p)) ?? '',
        )
      ) {
        void tg(botToken, 'deleteMessage', { chat_id: m.chat.id, message_id: m.message_id });
      }
      try {
        await handleText(botToken, m.chat.id, m.text);
      } catch (err) {
        log.error('Token bot: handler failed', { err });
      }
    }
  }
}

onHostStart(() => {
  const botToken = readEnvFile(['TELEGRAM_TOKEN_BOT_TOKEN']).TELEGRAM_TOKEN_BOT_TOKEN;
  if (!botToken) return;
  stopped = false;
  abort = new AbortController();
  void tg(botToken, 'deleteWebhook');
  void pollLoop(botToken, abort.signal);
  log.info('Telegram token bot started');
});

onHostShutdown(() => {
  stopped = true;
  abort?.abort();
});
