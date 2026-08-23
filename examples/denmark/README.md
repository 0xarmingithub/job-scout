# Denmark example

A worked setup for a job search in Denmark. Run it with:

```bash
pip install -e ".[all]"
playwright install chromium --with-deps
job-scout run --config-dir examples/denmark
```

The candidate in `profile.yaml` is fictional. The configuration around them is
the shape of a real daily deployment.

## Why Denmark is a useful example

Three things here do not appear in the default config, and each one is a
different lesson.

**A national board nothing else indexes.** [jobindex.dk](https://www.jobindex.dk)
carries a large share of Danish postings that never reach LinkedIn or Indeed. It
renders its results in the browser, so it needs Playwright and a headless
Chromium, the most expensive source in this repo to set up, and worth it if you
are searching in Denmark. Most countries have an equivalent. Look for yours.

**A non-English locale.** Careerjet runs with `locale_code: da_DK`, which returns
Danish-language listings that English search terms would otherwise miss. The
search terms stay in English; the locale is what widens the net.

**Two different disqualifiers, and they are not the same thing.** Roughly a third
of Danish postings need fluent or professional Danish. Separately, public-sector
and defence-adjacent roles need Danish or EU citizenship. Permanent residence is
not citizenship. The scorer returns `language_barrier` and
`work_authorization_barrier` as separate flags, and this profile fills in both
sides so it can.

## Numbers from the real deployment

| | |
|---|---|
| Sources | LinkedIn, Indeed, JobIndex, Careerjet |
| Searches | 8 terms, all four sources each |
| Threshold | 70 |
| Typical run | about 12 minutes end to end |
| Longest measured run | 736 seconds. 57 new postings recorded, 3 sent |
| Schedule | daily at 12:00 Europe/Copenhagen |
| Host | an Oracle Cloud always-free VM |

## What to change first

1. `profile.yaml`, all of it. It decides what counts as a match.
2. `hard_exclude_location_patterns`, the list here removes everything outside
   the Capital Region. Yours will be different.
3. The eight search terms in `config.yaml`.
4. `notify_threshold`. Start at 70 with four sources, 65 with two.

## If you are not in Denmark

Copy this folder, then:

- Drop `jobindex` from the `sites` lists and remove the Playwright install step.
- Change `careerjet.locale_code` to your country's. `de_DE`, `fr_FR`, `nl_NL`,
  `en_GB`, `en_US`. The full list is on
  [Careerjet's partner page](https://www.careerjet.com/partners/api).
- Replace the location exclusions with the places you will not commute to.
- Look for a national board like JobIndex and write a source for it.
  [docs/adding-a-job-source.md](../../docs/adding-a-job-source.md) is about 40
  lines of work.
