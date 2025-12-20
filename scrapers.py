# scrapers.py
import re
import requests
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup


def extract_ashby_board(ashby_url: str) -> str:
    # https://jobs.ashbyhq.com/companyName -> "companyName"
    return urlparse(ashby_url).path.strip("/").split("/")[-1]


def scrape_ashby(board_name: str):
    url = f"https://api.ashbyhq.com/posting-api/job-board/{board_name}"
    data = requests.get(url, timeout=20).json()

    results = []
    for job in data["jobs"]:
        # Use applyUrl if available; otherwise jobUrl
        link = job.get("applyUrl") or job.get("jobUrl")

        # Create a stable id from the URL (Ashby API doesn’t guarantee a numeric id field here)
        job_id = link.split("/")[-1] if link else f"{job.get('title','')}_{job.get('publishedAt','')}"

        results.append(
            {
                "source": "ashby",
                "company": board_name,
                "job_id": job_id,
                "title": job.get("title"),
                "location": job.get("location"),
                "url": link,
            }
        )
    return results

def scrape_workday(careers_page_url: str, jobs_api_url: str, *, max_pages: int = 50):
    """
    Workday CXS scraper:
      1) GET careers page to obtain session cookies
      2) POST to /wday/cxs/.../jobs with pagination

    careers_page_url example: https://vrtx.wd501.myworkdayjobs.com/vertex_careers
    jobs_api_url example:     https://vrtx.wd501.myworkdayjobs.com/wday/cxs/vrtx/vertex_careers/jobs
    """
    s = requests.Session()

    # Step 1: seed cookies/session
    s.get(careers_page_url, timeout=30)

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": careers_page_url.split("/vertex_careers")[0] if "/vertex_careers" in careers_page_url else None,
        "Referer": careers_page_url,
        "User-Agent": "Mozilla/5.0",
    }
    # Remove None header values
    headers = {k: v for k, v in headers.items() if v is not None}

    results = []
    offset = 0
    limit = 20

    for _ in range(max_pages):
        payload = {
            "appliedFacets": {},
            "limit": limit,
            "offset": offset,
            "searchText": "",
        }

        r = s.post(jobs_api_url, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()

        # Workday CXS commonly returns postings in jobPostings, but keep fallbacks
        postings = data.get("jobPostings") or data.get("items") or data.get("postings") or []

        if not postings:
            break

        for p in postings:
            title = p.get("title") or p.get("jobTitle")

            # externalPath is commonly a relative URL like "/en-US/Vertex_Careers/job/...."
            url = p.get("externalPath") or p.get("url")

            location = p.get("locationsText") or p.get("location")

            # Try to find a stable identifier
            job_id = p.get("id") or p.get("jobReqId") or url or title

            if url and url.startswith("/"):
                origin = careers_page_url.split("/")[0] + "//" + careers_page_url.split("/")[2]
                url = origin + url

            results.append(
                {
                    "source": "workday",
                    "company": careers_page_url,  # main.py will overwrite with friendly company name
                    "job_id": str(job_id),
                    "title": title,
                    "location": location,
                    "url": url,
                }
            )

        offset += limit

    return results


def scrape_greenhouse(board_token: str):
    """
    Scrape a Greenhouse job board and return a list of jobs.

    Example:
        jobs = scrape_greenhouse("cellarity")
    """
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs"
    data = requests.get(url, timeout=20).json()

    jobs = data["jobs"]  # list of job dicts
    results = []

    for job in jobs:
        results.append(
            {
                "source": "greenhouse",
                "company": board_token,
                "job_id": job["id"],
                "title": job["title"],
                "location": job["location"]["name"] if job.get("location") else None,
                "url": job["absolute_url"],
            }
        )

    return results

def extract_lever_account(lever_url: str) -> str:
    # https://jobs.lever.co/tahoebio-ai/ -> "tahoebio-ai"
    path = urlparse(lever_url).path.strip("/")
    return path.split("/")[0]


def scrape_lever(account: str):
    url = f"https://api.lever.co/v0/postings/{account}?mode=json"
    jobs = requests.get(url, timeout=20).json()  # lever returns a LIST

    results = []
    for job in jobs:
        results.append(
            {
                "source": "lever",
                "company": account,
                "job_id": job.get("id") or job.get("postingId") or job.get("text"),
                "title": job.get("text"),
                "location": job.get("categories", {}).get("location"),
                "url": job.get("hostedUrl") or job.get("applyUrl"),
            }
        )
    return results


def extract_smartrecruiters_company(smartrecruiters_url: str) -> str:
    # https://jobs.smartrecruiters.com/companyName -> "companyName"
    # or https://companyName.smartrecruiters.com/ -> "companyName"
    parsed = urlparse(smartrecruiters_url)
    path = parsed.path.strip("/")
    if path:
        # URL has a path component
        return path.split("/")[0]
    else:
        # URL is subdomain-based
        subdomain = parsed.netloc.split(".")[0]
        return subdomain


def scrape_smartrecruiters(company_identifier: str, *, limit: int = 100):
    """
    SmartRecruiters Posting API.
    Docs: GET /v1/companies/{companyIdentifier}/postings
    """
    url = f"https://api.smartrecruiters.com/v1/companies/{company_identifier}/postings"
    params = {"limit": limit, "offset": 0}
    results = []

    while True:
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        data = r.json()

        postings = data.get("content", [])  # PostingList typically uses 'content'
        if not postings:
            break

        for p in postings:
            posting_id = p.get("id") or p.get("uuid") or p.get("ref")
            
            # SmartRecruiters typically provides a 'ref' field with the job URL
            # If not, construct it from the company identifier and posting ID
            job_url = p.get("ref")
            if not job_url and posting_id:
                job_url = f"https://jobs.smartrecruiters.com/{company_identifier}/{posting_id}"
            
            location = p.get("location")
            location_str = None
            if isinstance(location, dict):
                location_str = location.get("city")
                if location.get("country"):
                    if location_str:
                        location_str += f", {location.get('country')}"
                    else:
                        location_str = location.get("country")
            elif isinstance(location, str):
                location_str = location
            
            results.append(
                {
                    "source": "smartrecruiters",
                    "company": company_identifier,
                    "job_id": str(posting_id),
                    "title": p.get("name"),
                    "location": location_str,
                    "url": job_url,
                }
            )

        # pagination: if fewer than limit returned, stop
        if len(postings) < params["limit"]:
            break
        params["offset"] += params["limit"]

    return results


def scrape_deshawresearch_current_opportunities(
    url: str = "https://www.deshawresearch.com/current-opportunities.html",
):
    """
    Scrape DESRES current-opportunities page.
    Returns list of dicts: {source, company, job_id, title, location, url}
    """
    r = requests.get(url, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    results = []

    # The page uses H5 headings for each job title (as of Dec 2025)
    for h in soup.select("h5"):
        title = h.get_text(strip=True)

        if not title:
            continue

        # Find the next "Apply Now" link after this heading
        apply_a = None
        for a in h.find_all_next("a", href=True, limit=50):
            if a.get_text(strip=True).lower() == "apply now":
                apply_a = a
                break
            # stop if we hit the next job heading
            if a.find_previous("h5") is not None and a.find_previous("h5") != h:
                break

        if not apply_a:
            continue

        apply_url = urljoin(url, apply_a["href"])

        # Stable-ish job_id: if their apply link contains an ID, use it; else use URL
        m = re.search(r"(\d{6,})", apply_url)
        job_id = m.group(1) if m else apply_url

        results.append(
            {
                "source": "deshawresearch",
                "company": "D. E. Shaw Research",  # main.py will overwrite with friendly company name
                "job_id": str(job_id),
                "title": title,
                "location": None,
                "url": apply_url,
            }
        )

    return results


def scrape_bamboohr(subdomain: str):
    """
    Scrape BambooHR jobs from a company's careers page.
    Returns list of dicts: {source, company, job_id, title, location, url}
    """
    url = f"https://{subdomain}.bamboohr.com/careers/list?format=json"
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()

    # shape varies; commonly data["jobs"], data["result"], or data itself
    if isinstance(data, list):
        jobs = data
    elif isinstance(data, dict):
        jobs = data.get("jobs") or data.get("result") or []
    else:
        jobs = []

    results = []
    for j in jobs:
        # Skip if j is not a dict (shouldn't happen, but be safe)
        if not isinstance(j, dict):
            continue
            
        job_id = str(j.get("id") or j.get("jobId") or j.get("jobOpeningId") or j.get("job_id") or "")
        title = j.get("jobOpeningName") or j.get("title")
        
        # Handle location - can be string or object
        location = j.get("location")
        if isinstance(location, dict):
            # Extract location from object
            location_parts = []
            if location.get("city"):
                location_parts.append(location["city"])
            if location.get("state"):
                location_parts.append(location["state"])
            if location.get("country"):
                location_parts.append(location["country"])
            # Also check atsLocation
            if not location_parts:
                ats_loc = j.get("atsLocation", {})
                if ats_loc.get("city"):
                    location_parts.append(ats_loc["city"])
                if ats_loc.get("state"):
                    location_parts.append(ats_loc["state"])
                if ats_loc.get("country"):
                    location_parts.append(ats_loc["country"])
            location = ", ".join(location_parts) if location_parts else None
        elif not location:
            # Try locationName or atsLocation
            location = j.get("locationName")
            if not location:
                ats_loc = j.get("atsLocation", {})
                if isinstance(ats_loc, dict):
                    location_parts = []
                    if ats_loc.get("city"):
                        location_parts.append(ats_loc["city"])
                    if ats_loc.get("state"):
                        location_parts.append(ats_loc["state"])
                    if ats_loc.get("country"):
                        location_parts.append(ats_loc["country"])
                    location = ", ".join(location_parts) if location_parts else None
        
        job_url = j.get("url") or j.get("jobOpeningUrl") or j.get("jobUrl")
        
        # Construct full URL if relative or missing
        if job_url and not job_url.startswith("http"):
            job_url = f"https://{subdomain}.bamboohr.com{job_url}" if job_url.startswith("/") else f"https://{subdomain}.bamboohr.com/{job_url}"
        elif not job_url:
            # Construct URL from job ID if available
            if job_id:
                job_url = f"https://{subdomain}.bamboohr.com/careers/{job_id}"
        
        results.append({
            "source": "bamboo",
            "company": subdomain,  # main.py will overwrite with friendly company name
            "job_id": job_id if job_id else job_url or title,
            "title": title,
            "location": location,
            "url": job_url,
        })
    
    return results


def scrape_dover_job_groups(client_id: str, cf_clearance: str = None):
    """
    Scrape Dover job groups using their API.
    Returns raw JSON response.
    """
    url = f"https://app.dover.com/api/v1/job-groups/{client_id}/job-groups"
    cookies = {}
    if cf_clearance:
        cookies["cf_clearance"] = cf_clearance
    
    r = requests.get(
        url,
        cookies=cookies if cookies else None,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def scrape_dover(client_id: str, cf_clearance: str = None):
    """
    Scrape Dover jobs from job groups.
    Returns list of dicts: {source, company, job_id, title, location, url}
    """
    data = scrape_dover_job_groups(client_id, cf_clearance)
    
    results = []
    
    # Handle different response structures
    job_groups = data if isinstance(data, list) else data.get("jobGroups", data.get("jobs", []))
    
    for group in job_groups:
        if not isinstance(group, dict):
            continue
        
        # Extract jobs from the group
        jobs = group.get("jobs", [])
        if not jobs:
            # If the group itself is a job, treat it as a single job
            if group.get("title") or group.get("name"):
                jobs = [group]
        
        for job in jobs:
            if not isinstance(job, dict):
                continue
            
            job_id = str(job.get("id") or job.get("jobId") or job.get("job_id") or "")
            title = job.get("title") or job.get("name") or job.get("jobTitle")
            location = job.get("location") or job.get("locationName") or job.get("city")
            job_url = job.get("url") or job.get("jobUrl") or job.get("applyUrl")
            
            # Construct full URL if relative or missing
            if job_url and not job_url.startswith("http"):
                job_url = f"https://app.dover.com{job_url}" if job_url.startswith("/") else f"https://app.dover.com/{job_url}"
            elif not job_url and job_id:
                job_url = f"https://app.dover.com/jobs/{job_id}"
            
            results.append({
                "source": "dover",
                "company": client_id,  # main.py will overwrite with friendly company name
                "job_id": job_id if job_id else job_url or title,
                "title": title,
                "location": location,
                "url": job_url,
            })
    
    return results


def scrape_polymer_board(board_url: str):
    """
    Scrape Polymer job board by finding job links.
    Returns list of dicts: {source, company, job_id, title, location, url}
    """
    r = requests.get(board_url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    results = []
    seen_job_ids = set()

    for a in soup.select('a[href]'):
        href = a.get("href", "")
        # Polymer "View job" links typically look like /12345 or full https://jobs.<domain>/12345
        m = re.search(r"/(\d{3,})/?$", href)
        if not m:
            continue

        job_id = m.group(1)
        
        # Skip duplicates
        if job_id in seen_job_ids:
            continue
        seen_job_ids.add(job_id)

        url = urljoin(board_url, href)
        title = a.get_text(strip=True)

        if not title:
            continue

        results.append({
            "source": "polymer",
            "company": board_url,  # main.py will overwrite with friendly company name
            "job_id": job_id,
            "title": title,
            "location": None,  # Location not easily extractable from link text
            "url": url,
        })

    return results


def scrape_pinpoint_jobs(board_url: str):
    """
    Scrape jobs from a Pinpoint HQ career board.
    Returns list of dicts: {source, company, job_id, title, location, url}
    E.g., board_url = "https://bighatbiosciences.pinpointhq.com/postings.json"
    """
    # Normalize base - remove /postings.json if present to get base URL
    base_url = board_url
    if board_url.endswith("/postings.json"):
        base_url = board_url[:-14]
    elif board_url.endswith("/"):
        base_url = board_url[:-1]
    
    # Use the provided URL if it includes postings.json, otherwise construct it
    if "/postings.json" in board_url:
        api_url = board_url
    else:
        api_url = f"{base_url}/postings.json"
    
    results = []
    page = 1

    while True:
        params = {"page": page, "per_page": 100}
        r = requests.get(api_url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()

        # Handle different response structures: {"data": [...]} or direct list
        jobs = data.get("data", []) if isinstance(data, dict) else data
        
        if not isinstance(jobs, list) or len(jobs) == 0:
            break

        for j in jobs:
            if not isinstance(j, dict):
                continue
                
            job_id = str(j.get("id") or j.get("uuid") or "")
            title = j.get("title") or j.get("name")
            
            # Extract location - can be in "location" (dict) or "locations" (array)
            location = None
            if j.get("location"):
                loc_obj = j["location"]
                if isinstance(loc_obj, dict):
                    # Use "name" if available, otherwise construct from city/province
                    location = loc_obj.get("name")
                    if not location and loc_obj.get("city"):
                        if loc_obj.get("province"):
                            location = f"{loc_obj['city']}, {loc_obj['province']}"
                        else:
                            location = loc_obj.get("city")
                else:
                    location = str(loc_obj)
            elif j.get("locations"):
                if isinstance(j["locations"], list) and len(j["locations"]) > 0:
                    loc_obj = j["locations"][0]
                    if isinstance(loc_obj, dict):
                        location = loc_obj.get("name") or loc_obj.get("city")
                        if not location and loc_obj.get("city") and loc_obj.get("province"):
                            location = f"{loc_obj['city']}, {loc_obj['province']}"
                    else:
                        location = str(loc_obj)
            
            # Construct job URL
            job_url = f"{base_url}/en/postings/{j.get('id') or j.get('uuid')}"
            
            results.append({
                "source": "pinpoint",
                "company": base_url,  # main.py will overwrite with friendly company name
                "job_id": job_id if job_id else job_url or title,
                "title": title,
                "location": location,
                "url": job_url,
            })

        # Check if there are more pages (if response has pagination info)
        if isinstance(data, dict):
            # If it's a dict with data, check if we got fewer than per_page
            if len(jobs) < params.get("per_page", 100):
                break
        else:
            # If it's a direct list, stop after first page
            break
        
        page += 1

    return results


def scrape_avature_jobs(base_search_url: str, per_page: int = 6):
    """
    Scrape Avature job board.
    Returns list of dicts: {source, company, job_id, title, location, url}
    
    base_search_url example:
      https://broadinstitute.avature.net/en_US/careers
    """
    base_search_url = base_search_url.rstrip("/")
    sess = requests.Session()

    results = []
    offset = 0

    while True:
        url = f"{base_search_url}/SearchJobs/?jobOffset={offset}&jobRecordsPerPage={per_page}"
        r = sess.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Titles are H3 links on this site
        links = soup.select("h3 a")
        if not links:
            break

        for a in links:
            title = a.get_text(strip=True)
            job_url = urljoin(base_search_url + "/", a.get("href", ""))

            # Avature pages usually show "Ref #12345 • Posted 11-Aug-2025 • On-Site"
            parent = a.find_parent()
            meta_text = parent.get_text(" ", strip=True) if parent else ""

            m_ref = re.search(r"Ref\s*#\s*([0-9]+)", meta_text)
            m_posted = re.search(r"Posted\s+([0-9]{2}-[A-Za-z]{3}-[0-9]{4})", meta_text)
            m_mode = re.search(r"Posted.*?\u2022\s*(On-Site|Hybrid|Remote)\b", meta_text)

            job_id = m_ref.group(1) if m_ref else job_url
            work_mode = m_mode.group(1) if m_mode else None
            
            # Use work_mode as location hint if available
            location = work_mode if work_mode else None

            results.append({
                "source": "avature",
                "company": base_search_url,  # main.py will overwrite with friendly company name
                "job_id": str(job_id),
                "title": title,
                "location": location,
                "url": job_url,
            })

        offset += per_page

    return results

