# main.py
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlparse

import yaml

from scrapers import scrape_greenhouse, scrape_lever, extract_lever_account, scrape_ashby, extract_ashby_board, scrape_workday, scrape_smartrecruiters, extract_smartrecruiters_company, scrape_bamboohr, scrape_dover, scrape_polymer_board, scrape_pinpoint_jobs, scrape_avature_jobs
from filters import score_job


DB_PATH = "jobs.db"
YAML_PATH = "companies.yaml"


def extract_greenhouse_token(greenhouse_url: str) -> str:
    # e.g. https://job-boards.greenhouse.io/cellarity -> "cellarity"
    return urlparse(greenhouse_url).path.strip("/").split("/")[-1]


def construct_workday_jobs_api_url(careers_url: str) -> str:
    # e.g. https://vrtx.wd501.myworkdayjobs.com/vertex_careers
    # -> https://vrtx.wd501.myworkdayjobs.com/wday/cxs/vrtx/vertex_careers/jobs
    parsed = urlparse(careers_url)
    netloc = parsed.netloc  # e.g. vrtx.wd501.myworkdayjobs.com
    path = parsed.path.strip("/")  # e.g. vertex_careers
    
    # Extract company code from subdomain (first part before .wd)
    company_code = netloc.split(".")[0]  # e.g. vrtx
    
    # Construct jobs API URL
    jobs_api_url = f"{parsed.scheme}://{netloc}/wday/cxs/{company_code}/{path}/jobs"
    return jobs_api_url


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS jobs (
            source      TEXT NOT NULL,
            company     TEXT NOT NULL,
            job_id      TEXT NOT NULL,
            title       TEXT,
            location    TEXT,
            url         TEXT,
            score       INTEGER DEFAULT 0,
            is_new      INTEGER DEFAULT 0,
            is_applied  INTEGER DEFAULT 0,
            first_seen  TEXT NOT NULL,
            last_seen   TEXT NOT NULL,
            PRIMARY KEY (source, company, job_id)
        );
        """
    )
    # Add score column if it doesn't exist (for existing databases)
    try:
        conn.execute("ALTER TABLE jobs ADD COLUMN score INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists
    # Add is_new column if it doesn't exist (for existing databases)
    try:
        conn.execute("ALTER TABLE jobs ADD COLUMN is_new INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists
    # Add is_applied column if it doesn't exist (for existing databases)
    try:
        conn.execute("ALTER TABLE jobs ADD COLUMN is_applied INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists
    conn.commit()


def load_companies(yaml_path: str):
    with open(yaml_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    return cfg.get("companies", [])


def recalculate_all_scores(conn: sqlite3.Connection) -> int:
    """
    Recalculate scores for all jobs in the database.
    Useful when scoring rules change.
    Returns number of jobs updated.
    """
    cur = conn.execute("SELECT source, company, job_id, title, location FROM jobs")
    jobs = cur.fetchall()
    
    updated = 0
    for source, company, job_id, title, location in jobs:
        job = {"title": title, "location": location}
        job_score = score_job(job)
        
        conn.execute(
            "UPDATE jobs SET score=? WHERE source=? AND company=? AND job_id=?",
            (job_score, source, company, job_id),
        )
        updated += 1
    
    conn.commit()
    return updated


def get_jobs_by_score(conn: sqlite3.Connection, min_score: int = None, limit: int = None) -> list[dict]:
    """
    Get jobs sorted by score (highest first).
    Optionally filter by minimum score and limit results.
    """
    query = "SELECT source, company, job_id, title, location, url, score, first_seen, last_seen FROM jobs"
    params = []
    
    if min_score is not None:
        query += " WHERE score >= ?"
        params.append(min_score)
    
    query += " ORDER BY score DESC, last_seen DESC"
    
    if limit:
        query += " LIMIT ?"
        params.append(limit)
    
    cur = conn.execute(query, params)
    rows = cur.fetchall()
    
    return [
        {
            "source": row[0],
            "company": row[1],
            "job_id": row[2],
            "title": row[3],
            "location": row[4],
            "url": row[5],
            "score": row[6],
            "first_seen": row[7],
            "last_seen": row[8],
        }
        for row in rows
    ]


def upsert_jobs(conn: sqlite3.Connection, jobs: list[dict]) -> list[dict]:
    """
    Insert jobs we haven't seen; update last_seen for jobs we have.
    Calculates and stores score for each job.
    Returns list of NEW jobs (inserted this run).
    """
    now = utc_now_iso()
    new_jobs = []

    for j in jobs:
        source = j["source"]
        company = j["company"]
        job_id = str(j["job_id"])
        title = j.get("title")
        location = j.get("location")
        url = j.get("url")
        
        # Calculate score for this job
        job_score = score_job(j)

        cur = conn.execute(
            """
            SELECT 1 FROM jobs
            WHERE source=? AND company=? AND job_id=?
            """,
            (source, company, job_id),
        )
        exists = cur.fetchone() is not None

        if exists:
            conn.execute(
                """
                UPDATE jobs
                SET title=?, location=?, url=?, score=?, is_new=0, last_seen=?
                WHERE source=? AND company=? AND job_id=?
                """,
                (title, location, url, job_score, now, source, company, job_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO jobs (source, company, job_id, title, location, url, score, is_new, is_applied, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?)
                """,
                (source, company, job_id, title, location, url, job_score, now, now),
            )
            new_jobs.append(j)

    conn.commit()
    return new_jobs


def main():
    companies = load_companies(YAML_PATH)
    if not companies:
        print(f"No companies found in {YAML_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    all_new = []

    for c in companies:
        name = c.get("name") or "Unknown"
        company_type = c.get("type")
        
        if company_type == "greenhouse":
            greenhouse_url = c.get("greenhouse_url") or c.get("url")
            if not greenhouse_url:
                print(f"Skipping {name}: missing greenhouse_url")
                continue

            token = extract_greenhouse_token(greenhouse_url)

            try:
                jobs = scrape_greenhouse(token)
            except Exception as e:
                print(f"[ERROR] {name} ({token}): {e}")
                continue

        elif company_type == "lever":
            lever_url = c.get("url")
            if not lever_url:
                print(f"Skipping {name}: missing url")
                continue

            account = extract_lever_account(lever_url)

            try:
                jobs = scrape_lever(account)
            except Exception as e:
                print(f"[ERROR] {name} ({account}): {e}")
                continue

        elif company_type == "ashby":
            ashby_url = c.get("url")
            if not ashby_url:
                print(f"Skipping {name}: missing url")
                continue

            board_name = extract_ashby_board(ashby_url)

            try:
                jobs = scrape_ashby(board_name)
            except Exception as e:
                print(f"[ERROR] {name} ({board_name}): {e}")
                continue

        elif company_type == "workday":
            careers_url = c.get("url")
            if not careers_url:
                print(f"Skipping {name}: missing url")
                continue

            jobs_api_url = construct_workday_jobs_api_url(careers_url)

            try:
                jobs = scrape_workday(careers_url, jobs_api_url)
            except Exception as e:
                print(f"[ERROR] {name}: {e}")
                continue

        elif company_type == "smartrecruiters":
            smartrecruiters_url = c.get("url")
            if not smartrecruiters_url:
                print(f"Skipping {name}: missing url")
                continue

            company_identifier = extract_smartrecruiters_company(smartrecruiters_url)

            try:
                jobs = scrape_smartrecruiters(company_identifier)
            except Exception as e:
                print(f"[ERROR] {name} ({company_identifier}): {e}")
                continue

        elif company_type == "bamboo":
            subdomain = c.get("subdomain")
            if not subdomain:
                # Try to extract from URL if provided
                bamboo_url = c.get("url")
                if bamboo_url:
                    # Extract subdomain from URL like https://company.bamboohr.com
                    parsed = urlparse(bamboo_url)
                    subdomain = parsed.netloc.split(".")[0]
                else:
                    print(f"Skipping {name}: missing subdomain")
                    continue

            try:
                jobs = scrape_bamboohr(subdomain)
            except Exception as e:
                print(f"[ERROR] {name} ({subdomain}): {e}")
                continue

        elif company_type == "dover":
            client_id = c.get("client_id")
            cf_clearance = c.get("cf_clearance")  # Optional
            
            if not client_id:
                print(f"Skipping {name}: missing client_id")
                continue

            try:
                jobs = scrape_dover(client_id, cf_clearance)
            except Exception as e:
                print(f"[ERROR] {name} ({client_id}): {e}")
                continue

        elif company_type == "polymer":
            board_url = c.get("url")
            if not board_url:
                print(f"Skipping {name}: missing url")
                continue

            try:
                jobs = scrape_polymer_board(board_url)
            except Exception as e:
                print(f"[ERROR] {name}: {e}")
                continue

        elif company_type == "pinpoint":
            board_url = c.get("url")
            if not board_url:
                print(f"Skipping {name}: missing url")
                continue

            try:
                jobs = scrape_pinpoint_jobs(board_url)
            except Exception as e:
                print(f"[ERROR] {name}: {e}")
                continue

        elif company_type == "avature":
            base_search_url = c.get("url")
            if not base_search_url:
                print(f"Skipping {name}: missing url")
                continue

            try:
                jobs = scrape_avature_jobs(base_search_url)
            except Exception as e:
                print(f"[ERROR] {name}: {e}")
                continue

        else:
            print(f"Skipping {name}: unsupported type '{company_type}'")
            continue

        # overwrite company field with friendly name (optional)
        for j in jobs:
            j["company"] = name

        new_jobs = upsert_jobs(conn, jobs)
        if new_jobs:
            print(f"{name}: {len(new_jobs)} new job(s)")
            all_new.extend(new_jobs)
        else:
            print(f"{name}: no new jobs")

    conn.close()

    if all_new:
        print("\n=== NEW JOBS ===")
        # Sort new jobs by score (highest first)
        sorted_new = sorted(all_new, key=lambda j: score_job(j), reverse=True)
        for j in sorted_new:
            loc = f" ({j['location']})" if j.get("location") else ""
            score = score_job(j)
            print(f"[Score: {score:3d}] {j['company']}: {j['title']}{loc}\n  {j['url']}")
    else:
        print("\nNo new jobs found.")


if __name__ == "__main__":
    main()
