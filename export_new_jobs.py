#!/usr/bin/env python3
"""
Export new jobs (is_new=1) to CSV file in a dated folder.
"""
import sqlite3
import csv
import sys
import os
from datetime import datetime

DB_PATH = "jobs.db"


def export_new_jobs_to_csv():
    """Export all new jobs to CSV in a dated folder, sorted by score, then mark them as not new."""
    conn = sqlite3.connect(DB_PATH)
    
    cur = conn.execute(
        """
        SELECT source, company, job_id, title, location, url, score, first_seen, last_seen
        FROM jobs
        WHERE is_new = 1
        ORDER BY score DESC, last_seen DESC
        """
    )
    
    jobs = cur.fetchall()
    
    if not jobs:
        conn.close()
        print("No new jobs found.")
        return 0
    
    # Create dated folder (YYYY-MM-DD format)
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_dir = f"exports/{date_str}"
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = f"{output_dir}/new_jobs.csv"
    
    # Write to CSV
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # Header
        writer.writerow([
            'Source', 'Company', 'Job ID', 'Title', 'Location', 
            'URL', 'Score', 'First Seen', 'Last Seen'
        ])
        # Data rows
        for job in jobs:
            writer.writerow(job)
    
    # Mark exported jobs as not new
    conn.close()
    
    print(f"Exported {len(jobs)} new jobs to {output_file}")
    return len(jobs), output_file


def export_top_jobs_by_score(limit=50):
    """Export top N jobs by score to CSV, regardless of is_new status."""
    conn = sqlite3.connect(DB_PATH)
    
    today = datetime.now().strftime("%Y-%m-%d")

    cur = conn.execute(
        """
        SELECT source, company, job_id, title, location, url, score, first_seen, last_seen
        FROM jobs
        WHERE DATE(first_seen) = ?
        ORDER BY score DESC, last_seen DESC
        """,
        (today,)
    )
        
    jobs = cur.fetchall()
    
    if not jobs:
        print("No jobs found.")
        return 0
    
    # Create dated folder (YYYY-MM-DD format)
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_dir = f"exports/{date_str}/top-jobs"
    os.makedirs(output_dir, exist_ok=True)
    
    output_file = f"{output_dir}/top_{limit}_jobs.csv"
    
    # Write to CSV
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        # Header
        writer.writerow([
            'Source', 'Company', 'Job ID', 'Title', 'Location', 
            'URL', 'Score', 'First Seen', 'Last Seen'
        ])
        # Data rows
        for job in jobs:
            writer.writerow(job)
    
    print(f"Exported top {len(jobs)} jobs by score to {output_file}")
    return len(jobs), output_file


if __name__ == "__main__":
    # Export new jobs
    result = export_new_jobs_to_csv()
    if isinstance(result, tuple):
        count, output_file = result
    else:
        count = result
    
    # Export top 20 jobs by score
    top_result = export_top_jobs_by_score(limit=20)
    
    sys.exit(0 if count > 0 else 1)

