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

## Getting a free Oracle Cloud VM, step by step

Skip this if you already have a Linux box. This is the free option, and it is
the one the author uses.

### Which shape to pick

Oracle's Always Free tier has two very different machines.

| Shape | CPU | RAM | Instances | The catch |
|---|---|---|---|---|
| VM.Standard.E2.1.Micro | 1/8 OCPU, x86-64 | 1 GB | 2 | Slow and tight on memory, but always available |
| VM.Standard.A1.Flex | up to 2 OCPU, ARM64 | up to 12 GB | 1 or 2 | Often "out of capacity", and no Chromium |

**Take the E2.1.Micro unless you have a reason not to.** It is enough, and you
can create one immediately. The ARM shape has two problems: it is in such demand
that creation fails with "Out of host capacity" for hours or days at a time, and
Playwright publishes no Chromium build for ARM64 Linux, so the JobIndex source
cannot run there. Everything else works on ARM.

Oracle halved the ARM allowance from 4 OCPU and 24 GB to 2 OCPU and 12 GB in
June 2026. Older guides still quote the bigger number. Check the current
allowance on
[Oracle's Always Free page](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm).

### 1. Sign up

[cloud.oracle.com/free](https://www.oracle.com/cloud/free/). It asks for a card
to prove you are a person. Always Free resources do not charge it, and the
account stays Always Free after the 30-day trial credit expires.

**Choose your home region carefully. You cannot change it later**, and your free
resources only exist there. Pick the one closest to you.

### 2. Create the instance

Menu, then Compute, then Instances, then Create instance.

| Field | What to choose |
|---|---|
| Name | anything |
| Image | Canonical Ubuntu 24.04 |
| Shape | Change shape, then pick VM.Standard.E2.1.Micro. Oracle moves it between tabs; at the time of writing it is under "Specialty and previous generation". |
| Networking | leave the defaults, and keep "Assign a public IPv4 address" on |
| SSH keys | Generate a key pair for me, then **download both the private and public key** |

Look for the "Always Free eligible" label next to the shape before you create
it. If it is not there, you will be billed.

The private key downloads once. Lose it and the only fix is a new instance.

### 3. Connect

```bash
chmod 600 ~/Downloads/ssh-key-*.key
ssh -i ~/Downloads/ssh-key-*.key ubuntu@<your-public-ip>
```

The public IP is on the instance page. The user is `ubuntu` on Ubuntu images and
`opc` on Oracle Linux. Port 22 is open in the default security list already, so
there is no firewall rule to add.

### 4. Install

```bash
sudo apt-get update && sudo apt-get install -y git python3-venv rsync
git clone https://github.com/0xarmingithub/job-scout.git
cd job-scout
sudo bash deploy/install-systemd.sh
```

Then put your API key in `/opt/job-scout/.env`, edit
`/opt/job-scout/profile.yaml`, and run it once:

```bash
sudo systemctl start job-scout.service
sudo journalctl -u job-scout -f
```

### 5. Stop Oracle taking the machine back

This one catches people, and it is specific to this use case.

Oracle reclaims Always Free compute instances it considers idle. An instance is
idle when, across a 7-day window, **all** of these are true:

- CPU use, 95th percentile, below 20%
- network use below 20%
- memory use below 20%, on ARM shapes only

A scout that runs for twelve minutes a day is idle by that definition. You get
an email first, and then the instance is stopped.

Three ways out, cheapest first:

1. **Run something else on the box too.** A tiny always-on service is enough to
   keep network or CPU above the line. This is the honest answer if you were
   going to use the VM for something anyway.
2. **Upgrade to Pay As You Go.** Always Free resources stay free, and upgraded
   accounts are treated differently. You are billed only if you exceed the free
   allowances.
3. **Accept it and watch your email.** Reclamation stops the instance rather
   than deleting it, and you can restart it. Annoying, and you lose runs in the
   meantime.

Read
[Oracle's own description](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
before deciding. The policy changes.

Worth saying plainly: for a job that runs twelve minutes a day, a small paid VPS
from anyone at around 4 euros a month has none of this. No reclamation policy,
no capacity lottery, no shape to get wrong. Oracle is free, and free has a
price. Pick whichever annoyance you mind less.

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
