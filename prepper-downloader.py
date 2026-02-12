import os, requests, shutil, sys, json, re, argparse
from bs4 import BeautifulSoup
from tqdm import tqdm
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

# --- CONFIG ---
REPO_RAW_URL = "https://raw.githubusercontent.com/pshehane/patrick-kiwix-downloader-python/main/prepper-downloader.py"
MIRROR_BASE = "https://ftp.fau.de/kiwix/zim/"
CACHE_FILE = "mirror_cache.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def load_json(filename):
    if not os.path.exists(filename): return {}
    with open(filename, 'r') as f: return json.load(f)

def save_json(filename, data):
    with open(filename, 'w') as f: json.dump(data, f, indent=2)

def extract_date(filename):
    match = re.search(r"(\d{4}-\d{2})", filename)
    return match.group(1) if match else "N/A"

def probe_mirror_size(url):
    try:
        with requests.get(url, stream=True, headers=HEADERS, timeout=10) as r:
            size = r.headers.get('content-length')
            return float(size) / (2**30) if size else 0.0
    except: return 0.0

def get_mirror_data(dir_path, prefix, probe=False):
    if dir_path == "MANUAL": return None
    try:
        r = requests.get(f"{MIRROR_BASE}{dir_path}", headers=HEADERS, timeout=8)
        soup = BeautifulSoup(r.text, 'html.parser')
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.endswith('.zim') and href.startswith(prefix):
                size_gb = 0.0
                if probe:
                    size_gb = probe_mirror_size(f"{MIRROR_BASE}{dir_path}{href}")
                else:
                    row = a.find_parent('tr')
                    if row:
                        for col in row.find_all('td'):
                            text = col.get_text(strip=True).upper()
                            if any(u in text for u in ['G', 'M']):
                                val_match = re.search(r"(\d+\.?\d*)", text)
                                if val_match:
                                    val = float(val_match.group(1))
                                    size_gb = val if 'G' in text else val / 1024
                                    break
                links.append({"url": f"{MIRROR_BASE}{dir_path}{href}", "size_gb": size_gb, "date": extract_date(href)})
        links.sort(key=lambda x: x['date'])
        return links[-1] if links else None
    except: return None

def audit_disk(drive_path, catalog, mirror_cache, force_refresh=False):
    table = Table(title="Prep-Disk Command Center v3.4", show_lines=True, show_footer=True)
    table.add_column("ID", justify="center")
    table.add_column("Library", style="cyan", footer="TOTALS")
    table.add_column("Local Ver", justify="center")
    table.add_column("Local GB", justify="right")
    table.add_column("Mirror GB", justify="right")
    table.add_column("Status", justify="center")

    results = []
    local_files = os.listdir(drive_path)
    sum_local, sum_mirror = 0.0, 0.0
    _, _, free = shutil.disk_usage(drive_path)
    free_gb = free / (2**30)

    with console.status("[bold yellow]Scanning drive and consulting mirror cache..."):
        for idx, item in enumerate(catalog['zim_libraries']):
            # Use Cache unless force_refresh is requested
            mirror = mirror_cache.get(item['prefix'])
            if not mirror or force_refresh:
                mirror = get_mirror_data(item['path'], item['prefix'], probe=force_refresh)
                if mirror: mirror_cache[item['prefix']] = mirror

            local_match = next((f for f in local_files if f.startswith(item['prefix'])), None)
            l_date = extract_date(local_match) if local_match else "N/A"
            l_size = os.path.getsize(os.path.join(drive_path, local_match)) / (2**30) if local_match else 0.0
            m_size = mirror['size_gb'] if mirror else 0.0
            
            sum_local += l_size
            sum_mirror += m_size
            
            status = "[red]MISSING[/red]"
            if local_match:
                status = "[green]INSTALLED[/green]"
                if mirror and mirror['date'] > l_date: status = "[bold yellow]OUTDATED[/bold yellow]"
            elif m_size > free_gb:
                status = "[bold red]TOO BIG[/bold red]"
            
            table.add_row(str(idx+1), item['name'], l_date, f"{l_size:.1f}", f"{m_size:.1f}", status)
            results.append({"item": item, "mirror": mirror, "local": local_match, "local_date": l_date})

    table.columns[3].footer = f"{sum_local:.1f}"
    table.columns[4].footer = f"{sum_mirror:.1f}"
    console.print(table)
    console.print(f"Drive Free: [bold green]{free_gb:.1f} GB[/bold green]")
    save_json(CACHE_FILE, mirror_cache) # Save what we learned
    return results, free_gb

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", action="store_true")
    args, _ = parser.parse_known_args()
    
    catalog = load_json('catalog.json')
    mirror_cache = load_json(CACHE_FILE)
    
    drive_l = input("Enter Drive Letter: ").upper()
    drive_path = f"{drive_l}:\\"
    if not os.path.exists(drive_path): return

    refresh = False
    while True:
        results, free_gb = audit_disk(drive_path, catalog, mirror_cache, force_refresh=refresh)
        refresh = False
        console.print("\n[bold yellow]Actions:[/bold yellow]")
        console.print("[S] Sync Mirrors | [P] Probe Sizes (1KB) | [M] Manual/ID info | [Q] Exit")
        cmd = input("Choice: ").lower()

        if cmd == 'q': break
        elif cmd == 's': refresh = True
        elif cmd == 'p': refresh = True # Probe uses the same logic with probe=True
        elif cmd == 'm' or cmd.isdigit():
            idx = int(input("ID: ")) - 1 if cmd == 'm' else int(cmd) - 1
            res = results[idx]
            if res['item']['path'] == "MANUAL":
                console.print(Panel(f"URL: {res['item']['manual_url']}"))
            elif res['mirror']:
                console.print(Panel(f"Mirror Path: {res['mirror']['url']}\nDate: {res['mirror']['date']}\nSize: {res['mirror']['size_gb']:.2f} GB"))

if __name__ == "__main__":
    main()