import os
import json
import re
import requests

from bs4 import BeautifulSoup
from datetime import datetime
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress

console = Console()

# --- CONFIG ---
BASE_URL = "https://ftp.fau.de/kiwix/zim/"
OUTPUT_FILE = "zim_full_catalog.json"
# Root directories on the mirror to ignore (usually source/meta folders)
IGNORE_DIRS = ["../", "index.html", "MD5SUMS", "SHA256SUMS"]

def get_zim_links(url):
    """Fetches all links from a directory listing, splitting into dirs and ZIMs."""
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200: return [], []
        soup = BeautifulSoup(r.text, 'html.parser')
        
        zim_files = []
        sub_dirs = []
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href in IGNORE_DIRS or "://" in href: continue
            
            if href.endswith('.zim'):
                # We only want English content for this version
                if "_en_" in href.lower():
                    zim_files.append({
                        "filename": href,
                        "full_url": f"{url}{href}"
                    })
            elif href.endswith('/'):
                sub_dirs.append(f"{url}{href}")
                
        return zim_files, sub_dirs
    except Exception:
        return [], []

def parse_zim_id(filename):
    """
    Splits 'wikipedia_en_all_maxi_2026-01.zim' into 
    ('wikipedia_en_all_maxi', '2026-01')
    """
    match = re.search(r"^(.*?)(?=_(\d{4}-\d{2}))", filename)
    if match:
        return match.group(1), match.group(2)
    return filename, "0000-00"

def main():
    start_time = datetime.now()
    catalog = {}
    queue = [BASE_URL]
    visited_dirs = set()

    console.print(Panel(f"Starting Mirror Crawl\nTarget: {BASE_URL}", style="bold cyan"))

    with Progress() as progress:
        task = progress.add_task("[yellow]Crawling Mirror...", total=None)
        
        while queue:
            current_dir = queue.pop(0)
            if current_dir in visited_dirs: continue
            visited_dirs.add(current_dir)
            
            zims, dirs = get_zim_links(current_dir)
            
            # Process ZIM files found in this directory
            for z in zims:
                lib_id, date_stamp = parse_zim_id(z['filename'])
                
                # Deduplication: Keep only the most recent version
                if lib_id not in catalog or date_stamp > catalog[lib_id]['date']:
                    catalog[lib_id] = {
                        "filename": z['filename'],
                        "url": z['full_url'],
                        "date": date_stamp,
                        "lib_id": lib_id
                    }
            
            # Add new subdirectories to the queue
            queue.extend(dirs)
            progress.update(task, advance=1, description=f"Found {len(catalog)} unique English ZIMs...")

    # Final structure with metadata
    output_data = {
        "metadata": {
            "last_crawled": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_items": len(catalog),
            "source": BASE_URL
        },
        "libraries": catalog
    }

    with open(OUTPUT_FILE, "w", encoding='utf-8') as f:
        json.dump(output_data, f, indent=4)

    console.print(f"\n[bold green]Success![/bold green] Cataloged {len(catalog)} libraries.")
    console.print(f"Results saved to: [bold white]{OUTPUT_FILE}[/bold white]")

if __name__ == "__main__":
    main()