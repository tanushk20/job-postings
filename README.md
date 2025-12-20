# Job Postings Scraper

Automated job posting scraper that monitors multiple companies' career pages and tracks new job openings.

## Features

- Scrapes jobs from multiple platforms: Greenhouse, Lever, Ashby, Workday, SmartRecruiters, BambooHR, Dover, Polymer, Pinpoint, Avature
- Scoring system to rank jobs by relevance
- Tracks new vs. existing jobs
- Marks applied jobs
- Daily automated runs via GitHub Actions
- CSV exports saved to dated folders in the repository

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
playwright install chromium
```

2. Configure companies in `companies.yaml`

3. Run the scraper:
```bash
python main.py
```

## GitHub Actions Setup

The workflow runs daily at 6 AM UTC and saves new jobs to CSV files in the `exports/` folder, organized by date.

### Output

New jobs are exported to `exports/YYYY-MM-DD/new_jobs.csv` and automatically committed to the repository.

## Adjusting Schedule

Edit `.github/workflows/daily-scrape.yml` and modify the cron schedule:
- `0 6 * * *` = 6 AM UTC
- `0 11 * * *` = 6 AM EST (UTC-5)
- `0 14 * * *` = 6 AM PST (UTC-8)

## Database

Jobs are stored in `jobs.db` with the following columns:
- `source`: Job board source
- `company`: Company name
- `job_id`: Unique job identifier
- `title`: Job title
- `location`: Job location
- `url`: Job posting URL
- `score`: Relevance score
- `is_new`: 1 if new, 0 if seen before
- `is_applied`: 1 if applied, 0 otherwise
- `first_seen`: First time job was seen
- `last_seen`: Last time job was seen

