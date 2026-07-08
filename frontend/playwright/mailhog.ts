import { APIRequestContext, expect } from "@playwright/test";

const MAILHOG_BASE =
  process.env.MAILHOG_BASE_URL?.replace(/\/$/, "") ?? "https://mailhog.nunet.network";
const MAIL_INBOX_DOMAIN = process.env.MAIL_INBOX_DOMAIN ?? "mailhog.nunet.network";
const MAIL_SUBJECT_FRAGMENT =
  process.env.MAIL_SUBJECT_FRAGMENT ?? "Verify your NuNet onboarding request";
const MAIL_POLL_MS = Number(process.env.MAIL_POLL_DELAY_MS ?? 30_000);
const MAIL_TIMEOUT_MS = Number(process.env.MAIL_TIMEOUT_MS ?? 600_000);

function mailhogHeaders(): Record<string, string> {
  const username = process.env.MAILHOG_USERNAME;
  const password = process.env.MAILHOG_PASSWORD ?? "";
  if (!username) return {};
  const token = Buffer.from(`${username}:${password}`).toString("base64");
  return { Authorization: `Basic ${token}` };
}

type MailhogMessage = {
  ID?: string;
  Content?: { Headers?: Record<string, string[]>; Body?: string };
  To?: Array<{ Mailbox?: string; Domain?: string }>;
};

function headerValue(headers: Record<string, string[]> | undefined, key: string): string {
  if (!headers) return "";
  const match = Object.keys(headers).find((n) => n.toLowerCase() === key.toLowerCase());
  if (!match) return "";
  const value = headers[match];
  return Array.isArray(value) ? value.join(", ") : String(value ?? "");
}

function recipients(message: MailhogMessage): string[] {
  const out: string[] = [];
  for (const addr of message.To ?? []) {
    if (addr.Mailbox && addr.Domain) out.push(`${addr.Mailbox}@${addr.Domain}`);
  }
  const headerTo = headerValue(message.Content?.Headers, "To");
  if (headerTo) {
    headerTo.split(",").forEach((e) => {
      const t = e.trim();
      if (t) out.push(t);
    });
  }
  return out.map((r) => r.toLowerCase());
}

export async function waitForMail(
  request: APIRequestContext,
  mailbox: string,
  subjectFragment = MAIL_SUBJECT_FRAGMENT
): Promise<{ id: string; subject: string; body: string }> {
  const targetEmail = `${mailbox}@${MAIL_INBOX_DOMAIN}`.toLowerCase();
  const started = Date.now();

  while (Date.now() - started < MAIL_TIMEOUT_MS) {
    const resp = await request.get(`${MAILHOG_BASE}/api/v2/messages`, {
      headers: mailhogHeaders(),
      failOnStatusCode: false,
    });
    expect(resp.status(), "Mailhog inbox query").toBe(200);
    const items = ((await resp.json()) as { items?: MailhogMessage[] }).items ?? [];
    const match = items.find((msg) => {
      if (!recipients(msg).includes(targetEmail)) return false;
      if (!subjectFragment) return true;
      const subject = headerValue(msg.Content?.Headers, "Subject");
      return subject.toLowerCase().includes(subjectFragment.toLowerCase());
    });
    if (match?.ID) {
      return {
        id: match.ID,
        subject: headerValue(match.Content?.Headers, "Subject"),
        body: match.Content?.Body ?? "",
      };
    }
    await new Promise((r) => setTimeout(r, MAIL_POLL_MS));
  }

  throw new Error(`Timed out waiting for mail to ${targetEmail}`);
}
