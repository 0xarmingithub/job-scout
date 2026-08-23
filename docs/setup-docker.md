# Running it in Docker

Reasonable if you already run everything this way. It buys you a clean Python
environment and nothing else — the scout has no server, no database daemon and
no background process.

Note before you start: **Docker Compose has no scheduler.** The container runs
once and exits. Something outside it has to start it daily.

## The short version

```bash
git clone https://github.com/0xarmingithub/job-scout.git
cd job-scout

mkdir myconfig
docker build -t job-scout .
docker run --rm -v "$PWD/myconfig:/config" job-scout init /config

# edit myconfig/profile.yaml and myconfig/config.yaml
echo "GOOGLE_API_KEY=your-key" > myconfig/.env

docker compose run --rm scout check
docker compose run --rm scout run
```

Results are in the `job-scout-data` volume, at `/data/matches.md`.

## The two mounts, and why the second one matters

```yaml
volumes:
  - ./myconfig:/config:ro          # config.yaml, profile.yaml
  - job-scout-data:/data           # jobs.db, scout.log, matches.md
```

`/config` is read-only. The scout never writes there.

**`/data` must survive the container.** It holds `jobs.db`, which is what
remembers every posting you have already been shown. Without a named volume or a
bind mount, every run treats every posting as new and you get the same jobs every
day.

If you would rather see the output directly:

```yaml
  - ./data:/data
```

## Secrets

Keep them in `myconfig/.env`, which `docker-compose.yml` loads with `env_file`.
Do not put them in `docker-compose.yml` — that file usually ends up committed.

Passing them on the command line works too, and is what you want in CI:

```bash
docker run --rm \
  -e GOOGLE_API_KEY \
  -e TELEGRAM_BOT_TOKEN \
  -e TELEGRAM_CHAT_ID \
  -v "$PWD/myconfig:/config:ro" \
  -v job-scout-data:/data \
  job-scout run
```

Bare `-e NAME` passes the value through from your shell without it appearing in
`ps` output or your shell history.

## Scheduling it

### With cron on the host

```cron
0 12 * * * cd /home/you/job-scout && /usr/bin/docker compose run --rm scout run >> /var/log/job-scout.log 2>&1
```

### With a systemd timer on the host

`/etc/systemd/system/job-scout-docker.service`:

```ini
[Unit]
Description=Job Scout (Docker)
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=/home/you/job-scout
ExecStart=/usr/bin/docker compose run --rm scout run
TimeoutStartSec=2700
```

Pair it with the timer from [setup-systemd.md](setup-systemd.md), changing
`Unit=` to point here.

If you are already writing a systemd timer, consider skipping Docker entirely —
[setup-systemd.md](setup-systemd.md) is fewer moving parts.

## Adding the JobIndex source

The shipped image has no browser, because Chromium roughly triples its size and
only the Denmark example needs it.

If you want it, swap the base image for Playwright's, which already carries
Chromium and its system libraries:

```dockerfile
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

WORKDIR /app
COPY pyproject.toml README.md ./
COPY job_scout ./job_scout
RUN pip install --quiet ".[all]" && playwright install chromium
```

Expect the image to go from roughly 200 MB to roughly 1.5 GB.

## Checking a build

```bash
docker run --rm -v "$PWD/myconfig:/config:ro" job-scout check
```

Every backend and every notifier reports ready or not ready, with the reason.

To poke around inside:

```bash
docker run --rm -it --entrypoint bash job-scout
```

## Common problems

**"config.yaml not found."** `/config` is empty. Run
`docker run --rm -v "$PWD/myconfig:/config" job-scout init /config` — note the
missing `:ro`, since this one has to write.

**The same jobs arrive every day.** `/data` is not persisted. Check that
`docker volume ls` shows `job-scout-data` and that the container is actually
using it.

**Permission denied writing to /data.** The image runs as uid 10001. On a bind
mount, `chown -R 10001:10001 ./data` on the host, or use a named volume, which
does not have this problem.

**The container exits immediately with nothing in the log.** That is a run with
no matches. Check `/data/scout.log`.
