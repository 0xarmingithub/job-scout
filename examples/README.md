# Examples

## `denmark/`

A complete worked setup for a job search in Denmark: four sources including a
national board, a non-English Careerjet locale, and a profile with both a
language barrier and a work-authorisation barrier. Read
[denmark/README.md](denmark/README.md).

```bash
job-scout run --config-dir examples/denmark
```

## `outcomes.csv`

A filled-in example of the optional feedback file. Copy it next to your
`config.yaml`, replace the rows with your own applications, and the scorer is
told what actually converted for you.

```bash
cp examples/outcomes.csv ./outcomes.csv
```

Three columns are required. `title`, `company`, `status`, and any others are
ignored, so you can keep a date or a note alongside them. Statuses are matched
loosely: "rejected after final round" counts as rejected, "first screen booked"
counts as interviewing. See [../docs/scoring.md](../docs/scoring.md).

Everything works without this file. It is a way to make the scorer better, not a
thing you have to maintain.
