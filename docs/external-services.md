# Every outside service, and how to get set up with it

One page for every account, key and token this thing can use. Nothing here is
required except one scoring backend and one notifier.

If you only want the shortest path: get a **Google AI Studio** key, use the
**file** notifier, and stop reading. That is two minutes and no other accounts.

## The whole list

| Service | What it does here | Account? | Cost | Setup |
|---|---|---|---|---|
| [Google AI Studio](#google-ai-studio-scoring) | Scores postings. The default. | Google account | Free tier, no card | 2 min |
| [OpenRouter](#openrouter-scoring-alternative) | Scores postings, many models | Yes | Pay per token | 3 min |
| Claude / Grok / Codex CLI | Scores postings on a subscription you already pay for | The CLI, logged in | Your existing plan | Already done, or an install |
| LinkedIn | Job source | No | Free | Nothing, but read the terms note |
| Indeed | Job source | No | Free | Nothing, but read the terms note |
| Glassdoor, ZipRecruiter, Google Jobs | Job sources | No | Free | Nothing |
| [Careerjet](#careerjet-job-source) | Job source, licensed API | Yes | Free | A form, plus a fixed IP |
| [Apify](#apify-job-source-paid) | Job source, runs the scraping for you | Yes | $5/month free, then paid | 10 min |
| JobIndex | Job source, Denmark only | No | Free | A browser install, x86 only |
| [Telegram](#telegram-notifications) | Jobs on your phone | Telegram account | Free | 5 min |
| [Gmail or any SMTP](#email-notifications) | Jobs by email | Yes | Free | 5 min |
| [Slack](#slack-notifications) | Jobs in a channel | A workspace you can add apps to | Free | 5 min |
| [Discord](#discord-notifications) | Jobs in a channel | A server you own | Free | 2 min |
| [Oracle Cloud](setup-systemd.md#getting-a-free-oracle-cloud-vm-step-by-step) | A machine to run it on | Yes | Free tier, card for identity | 20 min |
| GitHub | Runs it on a schedule for free | Yes | Free | See [setup-github-actions.md](setup-github-actions.md) |

A note on the job boards, because it matters more than the setup effort.
**LinkedIn and Indeed both prohibit automated scraping in their terms.** They are
on by default because they are what produces results, and that is your decision
to make. Careerjet is a licensed API and Apify does the collection under its own
agreements, so those two are the lower-risk path. See the disclaimer in the
[README](../README.md#terms-of-service-plainly).

---

## Google AI Studio (scoring)

The default, and free.

1. Go to [aistudio.google.com/apikey](https://aistudio.google.com/apikey).
2. Sign in with a Google account.
3. Create API key.
4. Copy it into your `.env`:

   ```
   GOOGLE_API_KEY=AIza...
   ```

No card. The free tier allows well over a thousand model calls a day, and a run
makes 30 to 60 in steady state. Check the current limits on
[Google's pricing page](https://ai.google.dev/gemini-api/docs/pricing).

If a run later says the model was not found, the model name changed. Look up a
current one at
[ai.google.dev/gemini-api/docs/models](https://ai.google.dev/gemini-api/docs/models)
and put it in `scoring_model`.

## OpenRouter (scoring alternative)

Use this if you want a model Google does not offer.

1. [openrouter.ai/keys](https://openrouter.ai/keys), sign in, create a key.
2. Add credit. It is pay per token.
3. In `.env`:

   ```
   OPENROUTER_API_KEY=sk-or-...
   ```
4. In `config.yaml`:

   ```yaml
   scoring_model: "openrouter:google/gemini-2.5-flash"
   ```

## Careerjet (job source)

An aggregator with a licensed partner API. Worth setting up if you want
non-English listings, or if you would rather not scrape LinkedIn.

1. Go to [careerjet.com/partners/api](https://www.careerjet.com/partners/api).
2. Register. The form asks for the website that will use the API and the
   address it will call from. **Write down both.** The API rejects calls whose
   Referer and IP do not match what you registered, which is why all three
   values below are required and none has a default.
3. Put all three in `.env`:

   ```
   CAREERJET_API_KEY=...
   CAREERJET_REFERER=https://the-site-you-registered.example/jobs
   CAREERJET_USER_IP=the.public.ip.of.this.machine
   ```
4. Add `careerjet` to a search's `sites`, and set the locale for your market:

   ```yaml
   careerjet:
     locale_code: da_DK      # en_GB, en_US, de_DE, fr_FR, nl_NL ...
   ```

The locale is the point of this source in a non-English market. Your search
terms stay in English and `da_DK` still returns Danish-language listings.

**It will not work from GitHub Actions**, because a runner's IP changes every
run and Careerjet checks it.

## Apify (job source, paid)

Apify runs the scraping on its own machines through its own proxies. That is the
fix for LinkedIn and Indeed throttling datacenter addresses, and the only source
here that works properly from GitHub Actions.

Full walkthrough in
[setup-github-actions.md](setup-github-actions.md#making-apify-work-from-actions).
The short version:

1. Sign up at [apify.com](https://apify.com). Free plan includes $5 of usage a
   month and asks for no card.
2. Settings, then Integrations, then copy the Personal API token. It starts
   `apify_api_`.
3. `.env`:

   ```
   APIFY_API_TOKEN=apify_api_...
   ```
4. Pick an Actor from [apify.com/store](https://apify.com/store), read its
   pricing tab, and describe it under `apify:` in `config.yaml`.

There is no default Actor. Every one bills differently and none should start
charging you because a name appeared in a list.

## Telegram (notifications)

The one most people want. A message per job, on your phone.

1. Open Telegram and message [@BotFather](https://t.me/botfather).
2. Send `/newbot`. Give it a name, then a username ending in `bot`.
3. It replies with a token like `123456789:AAH...`. Copy it.
4. **Send your new bot any message.** A bot cannot start a conversation, so
   until you do this it cannot message you.
5. Open this in a browser, with your token in place of `<TOKEN>`:

   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```

   Find `"chat":{"id":123456789`. That number is your chat id.
6. `.env`:

   ```
   TELEGRAM_BOT_TOKEN=123456789:AAH...
   TELEGRAM_CHAT_ID=123456789
   ```
7. `config.yaml`:

   ```yaml
   notifiers:
     - type: file
     - type: telegram
   ```

`job-scout check` should now show telegram as READY. If it says "chat not
found", you skipped step 4.

## Email (notifications)

Works with any SMTP server. On Gmail it needs an App Password, not your normal
password.

1. Turn on 2-step verification on your Google account.
2. Create an App Password at
   [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
   You get 16 characters. Spaces in it do not matter.
3. `.env`:

   ```
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=you@gmail.com
   SMTP_PASSWORD=the16characters
   ```
4. `config.yaml`:

   ```yaml
   notifiers:
     - type: email
       to: you@example.com
   ```

Port 587 means STARTTLS and 465 means SSL. The port decides unless you set
`SMTP_SECURITY` yourself.

## Slack (notifications)

1. Go to [api.slack.com/apps](https://api.slack.com/apps) and click
   **Create New App**, then **From scratch**.
2. Name it, pick your workspace, create.
3. In the left sidebar, **Incoming Webhooks**. Turn the toggle **On**.
4. **Add New Webhook to Workspace** at the bottom, choose a channel, allow.
5. Copy the webhook URL. It looks like
   `https://hooks.slack.com/services/T000/B000/xxxx`.
6. `.env`:

   ```
   WEBHOOK_URL=https://hooks.slack.com/services/...
   ```
7. `config.yaml`:

   ```yaml
   notifiers:
     - type: webhook
       flavor: slack
   ```

Treat that URL as a password. Anyone holding it can post into your channel,
which is why it lives in `.env` and not in `config.yaml`.

## Discord (notifications)

The quickest of the four.

1. In a server you own: **Server Settings**, then **Integrations**, then
   **Webhooks**.
2. **New Webhook**, choose the channel, **Copy Webhook URL**.
3. `.env`:

   ```
   WEBHOOK_URL=https://discord.com/api/webhooks/...
   ```
4. `config.yaml`:

   ```yaml
   notifiers:
     - type: webhook
       flavor: discord
   ```

`flavor: discord` matters. Discord wants a `content` field where Slack wants
`text`, and the wrong one gives you a 400.

## Anything else that takes a JSON webhook

Mattermost, Google Chat, Zulip, ntfy and most others accept a plain
`{"text": "..."}` body:

```yaml
notifiers:
  - type: webhook
    flavor: raw
```

If your service needs a different shape, writing a notifier is about 30 lines.
See [adding-a-notifier.md](adding-a-notifier.md).

---

## What each field means

This page is about getting the credential. What the config fields do is in
[configuration.md](configuration.md). Run `job-scout check` at any point and it
will tell you exactly which of these you still need.
