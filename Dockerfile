# Job Scout in a container.
#
# Build:
#   docker build -t job-scout .
#
# Run once:
#   docker run --rm \
#     -v "$PWD/myconfig:/config" \
#     -v job-scout-data:/data \
#     --env-file myconfig/.env \
#     job-scout
#
# /config holds config.yaml and profile.yaml. /data holds the jobs database, the
# log, and anything the file notifier writes. Put it on a named volume, or the
# scout forgets every posting it has seen each time the container exits.
#
# The image does not include Playwright or Chromium, because that roughly
# triples its size and only the Denmark example needs it. If you want the
# JobIndex source, use the playwright base image instead. See the comment at
# the bottom.

FROM python:3.12-slim

LABEL org.opencontainers.image.title="job-scout"
LABEL org.opencontainers.image.description="Searches job boards daily, scores every posting against your profile, sends you the good ones."
LABEL org.opencontainers.image.source="https://github.com/0xarmingithub/job-scout"
LABEL org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    JOB_SCOUT_CONFIG_DIR=/config \
    JOB_SCOUT_DATA_DIR=/data

WORKDIR /app

# Dependencies first, so editing the source does not re-download the world.
COPY pyproject.toml README.md ./
COPY job_scout ./job_scout
RUN pip install --quiet ".[gemini,jobspy]"

# Run as a normal user. Nothing here needs root.
RUN useradd --create-home --uid 10001 scout \
    && mkdir -p /config /data \
    && chown -R scout:scout /config /data
USER scout

VOLUME ["/config", "/data"]

# With no config mounted, this seeds the example config into /config and runs
# against the fictional profile. Enough to see whether the thing works.
ENTRYPOINT ["job-scout"]
CMD ["run"]

# ─── For the JobIndex source (Denmark) ────────────────────────────────────────
# Replace the FROM line above with the Playwright image, which already carries
# Chromium and its system libraries, and install the jobindex extra:
#
#   FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy
#   RUN pip install --quiet ".[all]" && playwright install chromium
