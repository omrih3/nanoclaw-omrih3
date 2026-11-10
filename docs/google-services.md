# Connecting Gmail, Google Contacts and Google Sheets

Agents never hold Google credentials. They call the real Google APIs, and the
OneCLI gateway injects the OAuth token at the network boundary
(see [gateway-seam.md](gateway-seam.md)). Connecting a service means
authorizing it once in OneCLI and letting your agent use that connection.

## 1. Prerequisites

- OneCLI installed as the gateway (`/add-onecli`) and the host running.
- A Google account to authorize.
- Check what OneCLI offers: `onecli apps list` (look for `gmail`, `google-sheets`, and a Contacts/People entry).

## 2. Connect each service

In the OneCLI dashboard, open **Apps**, pick the service, and click **Connect**.
Sign in with Google and approve the scopes. Repeat for each:

| Service | Provider | API the agent calls |
|---------|----------|---------------------|
| Gmail | `gmail` | `https://gmail.googleapis.com/gmail/v1/users/me/...` |
| Google Contacts | `google-contacts` / People API | `https://people.googleapis.com/v1/people/me/connections` |
| Google Sheets | `google-sheets` | `https://sheets.googleapis.com/v4/spreadsheets/{id}` |

If the dashboard has no entry for one of them, check `onecli apps list`; if it
is missing, use the custom OAuth/Google app option and enable the API in your
own Google Cloud project (APIs & Services → Library → enable Gmail API,
People API, Google Sheets API; add the matching scopes below).

Suggested minimum scopes (prefer read-only unless the agent must write):

- Gmail: `gmail.readonly` (add `gmail.send` / `gmail.modify` only if needed)
- Contacts: `contacts.readonly`
- Sheets: `spreadsheets` (or `spreadsheets.readonly`)

## 3. Give the agent access

A connection is not automatically usable by every agent. Attach it to the
agent identity that your agent group runs as:

```bash
onecli agents list
onecli apps connections list
onecli agents grants attach-connection --id <agent-id> --connection-id <connection-id>
```

Optionally add approval rules in OneCLI so sends/writes (e.g. `POST .../messages/send`)
require human approval; see [Approvals in CLAUDE.md](../CLAUDE.md#approvals).

## 4. Verify

Message your agent, e.g. "list my 5 latest emails", "find the phone number
for <name>", "read cell A1 of sheet <id>". If a service is not connected the
gateway returns `app_not_connected` with a `connect_url`; the agent shows you
the link. Open it, authorize, and ask again.

Manual check from the container's point of view:

```bash
curl -s "https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults=1"
curl -s "https://people.googleapis.com/v1/people/me/connections?personFields=names,phoneNumbers&pageSize=1"
curl -s "https://sheets.googleapis.com/v4/spreadsheets/<SHEET_ID>/values/A1"
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `app_not_connected` | Connect the service in the OneCLI dashboard |
| 403 `insufficient scopes` | Reconnect with the needed scope (e.g. add `gmail.send`) |
| 403 `API has not been used` | Enable the API in your Google Cloud project (custom app only) |
| Agent says it has no access | Attach the connection to the agent (step 3), then `bash setup/lib/restart.sh` |
| 403 JSON policy error | A OneCLI rule blocked or held the request; check approvals |
