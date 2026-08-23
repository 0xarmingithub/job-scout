# Running it on a VM with a systemd timer

The path that actually works long-term. A small always-on Linux box, a timer that
fires once a day, and a notification on your phone.

The author runs this on an
[Oracle Cloud always-free VM](https://www.oracle.com/cloud/free/), which costs
nothing and is enough. Any $5 VPS, a Raspberry Pi, or a spare machine works.

Do [setup-local.md](setup-local.md) first. Tune the profile where you can see it,
then automate.

## The short version

```bash
git clone https://github.com/0xarmingithub/job-scout.git
cd job-scout
sudo bash deploy/install-systemd.sh
```

Then put your API key in `/opt/job-scout/.env`, edit
`/opt/job-scout/profile.yaml`, and run it once by hand:

```bash
sudo systemctl start job-scout.service
sudo journalctl -u job-scout -f
```

The installer copies the code to `/opt/job-scout`, builds a virtual environment,
writes the systemd units, and enables the timer. It never overwrites an existing
`.env`, `config.yaml`, `profile.yaml` or `jobs.db`, so re-running it after a
`git pull` is safe.

Options, all environment variables:

```bash
sudo INSTALL_DIR=/srv/job-scout \
     SERVICE_USER=scout \
     TIMEZONE=Europe/Berlin \
     RUN_AT=07:30:00 \
     EXTRAS=gemini,jobspy,jobindex \
     bash deploy/install-systemd.sh
```

## Doing it by hand

If you would rather not run someone else's install script — reasonable.

### 1. Install

```bash
sudo mkdir -p /opt/job-scout
sudo chown "$USER" /opt/job-scout
git clone https://github.com/0xarmingithub/job-scout.git /opt/job-scout
cd /opt/job-scout
python3 -m venv .venv
.venv/bin/pip install -e ".[gemini,jobspy]"
```

### 2. Configure

```bash
.venv/bin/job-scout init /opt/job-scout
cp job_scout/templates/.env.example .env
chmod 600 .env
nano .env             # your API key
nano profile.yaml     # you
nano config.yaml      # your searches
.venv/bin/job-scout check
```

`chmod 600 .env` matters. It is the only file on the box holding a credential.

### 3. The service

`/etc/systemd/system/job-scout.service`:

```ini
[Unit]
Description=Job Scout
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=/opt/job-scout
ExecStart=/opt/job-scout/.venv/bin/job-scout run
StandardOutput=journal
StandardError=journal
SyslogIdentifier=job-scout
TimeoutStartSec=2700

NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/job-scout/data
```

`TimeoutStartSec=2700` is 45 minutes. Sizing it: the author's four-source run
over eight terms takes about 12 minutes, and the longest measured was 736
seconds. 45 minutes leaves room for a slow day without letting a genuine hang
sit there all afternoon.

No `EnvironmentFile` line: the scout reads `/opt/job-scout/.env` itself, and
systemd's parser handles quoting differently from dotenv's.

### 4. The timer

`/etc/systemd/system/job-scout.timer`:

```ini
[Unit]
Description=Job Scout daily run

[Timer]
OnCalendar=*-*-* 12:00:00 Europe/Copenhagen
Persistent=true
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
```

Name a timezone rather than using UTC — systemd handles daylight saving for you.

`Persistent=true` earns its place: without it, a reboot at the wrong moment
silently costs you a day.

### 5. Start it

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now job-scout.timer
systemctl list-timers job-scout.timer
sudo systemctl start job-scout.service     # run once now
sudo journalctl -u job-scout -f
```

## Day-to-day

```bash
systemctl list-timers job-scout.timer      # when does it fire next
sudo journalctl -u job-scout -n 100        # the last run
sudo journalctl -u job-scout --since today
tail -f /opt/job-scout/data/scout.log      # the same, in the scout's own log
sudo systemctl start job-scout.service     # run now
```

### Updating

```bash
cd /opt/job-scout
git pull
.venv/bin/pip install -e ".[gemini,jobspy]"
.venv/bin/job-scout check
```

Your `config.yaml`, `profile.yaml`, `.env` and `data/` are all gitignored, so a
pull cannot touch them.

## Making failures reach you

A run that dies quietly is the failure that costs you a week. The scout sends any
run-level failure to your notifiers, with credentials stripped out of the message
first — so a broken key or a blocked source arrives on your phone rather than
sitting in a log.

That covers failures inside a run. It does not cover the run never starting. For
that, ask systemd to tell you:

```bash
sudo systemctl edit job-scout.service
```

```ini
[Unit]
OnFailure=job-scout-alert.service
```

with a `job-scout-alert.service` that sends you something. Or simply check
`systemctl list-timers` when a quiet day feels too quiet.

## Choosing an Oracle always-free shape

Oracle's free tier offers two very different machines, and the choice matters
here more than it looks.

| Shape | Architecture | Free allowance | Catch |
|---|---|---|---|
| VM.Standard.E2.1.Micro | x86-64 | 2 instances, 1 GB RAM each | Tight on memory. This is what the author runs. |
| VM.Standard.A1.Flex | ARM64 (Ampere) | 4 cores, 24 GB RAM total | **Playwright cannot install Chromium on ARM64 Linux.** |

If you want the JobIndex source, take the x86 shape. Playwright lists Ubuntu
arm64 as a supported platform, but Chromium is not published for it, so
`playwright install chromium` fails on Ampere. Everything else in the scout —
LinkedIn, Indeed, Careerjet, Apify, all five scoring backends — works fine on
ARM, so if you are not searching Denmark, take the ARM shape and its 24 GB.

Anywhere else with a Linux box, this section does not apply. Check with
`uname -m`: `x86_64` is fine, `aarch64` means no JobIndex.

## Small VMs

The always-free Oracle VM has under 1 GB of RAM, which is enough — but two things
matter:

- **The CLI backends need 200-400 MB each.** They run one at a time by default
  (`LLM_CLI_CONCURRENCY`). Leave that alone on a small box.
- **Chromium for the JobIndex source is heavy.** If you enable it on a 1 GB
  machine, add swap:

  ```bash
  sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  ```

## Using a CLI backend from a VM with no browser

The `claude`, `grok` and `codex` backends need an interactive login the first
time. On a headless box, run the CLI on a machine where you are already logged
in and point the VM at it over SSH:

```
LLM_CLI_SSH_HOST=you@your-laptop
LLM_CLI_SSH_KEY=/home/ubuntu/.ssh/id_ed25519
```

The prompt is sent base64-encoded over stdin, so quotes, newlines and emoji in a
job description cannot corrupt it.
