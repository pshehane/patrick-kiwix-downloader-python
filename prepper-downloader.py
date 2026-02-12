import os, requests, shutil, sys, json, re, argparse
from bs4 import BeautifulSoup
from tqdm import tqdm
from datetime import datetime
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
    try:
        with open(filename, 'r', encoding='utf-8') as f: return json.load(f)
    except: return {}

def save_json(filename, data):
    with open(filename, 'w', encoding='utf-8') as f: 
        json.dump(data, f, indent=2)

def extract_date(filename):
    match = re.search(r"(\d{4}-\d{2})", filename)
    return match.group(1) if match else "N/A"

def probe_mirror_size(url):
    """Attempts to get Content-Length without downloading full file."""
    try:
        with requests.get(url, stream=True, headers=HEADERS, timeout=10) as r:
            size = r.headers.get('content-length')
            if size: return float(size) / (2**30)
            return 0.0
    except Exception as e:
        return f"PROBE_FAIL: {str(e)[:50]}"

def get_mirror_data(dir_path, prefix, probe=False):
    """Aggressively searches for the latest ZIM version and logs results to cache."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    if dir_path == "MANUAL":
        return {"status": "MANUAL_ENTRY", "last_checked": timestamp}
    
    # Fallback paths in case the catalog path is outdated
    search_paths = [dir_path, "wikipedia/", "other/", "stack_exchange/", ""]
    
    for path in search_paths:
        try:
            target_url = f"{MIRROR_BASE}{path}"
            r = requests.get(target_url, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                continue

            soup = BeautifulSoup(r.text, 'html.parser')
            links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.endswith('.zim') and prefix in href:
                    size_gb = 0.0
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
                    links.append({"url": f"{target_url}{href}", "size_gb": size_gb, "date": extract_date(href)})
            
            if links:
                links.sort(key=lambda x: x['date'])
                latest = links[-1]
                
                # If size is 0 and probe is requested, try header check
                if probe:
                    console.print(f"  [dim]↳ Checking Headers: {latest['url'].split('/')[-1]}[/dim]")
                    p_size = probe_mirror_size(latest['url'])
                    if isinstance(p_size, float): 
                        latest['size_gb'] = p_size
                    else:
                        latest['error'] = p_size
                
                latest['status'] = "SUCCESS"
                latest['last_checked'] = timestamp
                latest['search_path_used'] = path
                return latest

        except Exception as e:
            continue

    return {"status": "NOT_FOUND", "last_checked": timestamp, "attempted_paths": search_paths}

def audit_disk(drive_path, catalog, mirror_cache, force_refresh=False):
    table = Table(title=f"Prep-Disk v3.7 (Cache: {len(mirror_cache)} entries)", show_lines=True, show_footer=True)
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

    console.print(f"\n[bold yellow]Auditing Knowledge...{' (Header Probe Active)' if force_refresh else ''}[/bold yellow]")
    
    for idx, item in enumerate(tqdm(catalog['zim_libraries'], desc="Scanning Mirror Paths")):
        # Update cache if forced OR if previous attempt failed
        if force_refresh or mirror_cache.get(item['prefix'], {}).get('status') != "SUCCESS":
            mirror_cache[item['prefix']] = get_mirror_data(item['path'], item['prefix'], probe=force_refresh)

        mirror = mirror_cache[item['prefix']]
        local_match = next((f for f in local_files if f.startswith(item['prefix'])), None)
        
        l_date = extract_date(local_match) if local_match else "N/A"
        l_size = os.path.getsize(os.path.join(drive_path, local_match)) / (2**30) if local_match else 0.0
        m_size = mirror.get('size_gb', 0.0)
        
        sum_local += l_size
        sum_mirror += m_size
        
        # Status Resolution
        status = "[red]MISSING[/red]"
        if mirror.get('status') != "SUCCESS" and mirror.get('status') != "MANUAL_ENTRY":
            status = f"[dim red]{mirror.get('status')}[/dim red]"
        elif local_match:
            status = "[green]INSTALLED[/green]"
            if mirror.get('status') == "SUCCESS" and mirror.get('date', "") > l_date:
                status = "[bold yellow]OUTDATED[/bold yellow]"
        elif m_size > free_gb:
            status = "[bold red]TOO BIG[/bold red]"
        elif mirror.get('status') == "MANUAL_ENTRY":
            status = "[blue]MANUAL[/blue]"
        
        table.add_row(str(idx+1), item['name'], l_date, f"{l_size:.1f}", f"{m_size:.1f}", status)
        results.append({"item": item, "mirror": mirror, "local": local_match, "local_date": l_date})

    table.columns[3].footer = f"{sum_local:.1f}"
    table.columns[4].footer = f"{sum_mirror:.1f}"
    console.print(table)
    save_json(CACHE_FILE, mirror_cache)
    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", action="store_true")
    args, _ = parser.parse_known_args()
    
    # Self Update Logic (Skips if --dev)
    if not args.dev:
        try:
            r = requests.get(REPO_RAW_URL, timeout=3, headers=HEADERS)
            if r.status_code == 200:
                with open(sys.argv[0], 'r', encoding='utf-8') as f:
                    if f.read() != r.text:
                        with open(sys.argv[0], 'w', encoding='utf-8') as f: f.write(r.text)
                        console.print("[green]Script Updated! Restarting...[/green]")
                        sys.exit()
        except: pass

    catalog = load_json('catalog.json')
    mirror_cache = load_json(CACHE_FILE)
    
    if not catalog:
        console.print("[red]Error: catalog.json missing.[/red]")
        return

    drive_l = input("Enter Drive Letter (e.g., F): ").upper()
    drive_path = f"{drive_l}:\\"
    if not os.path.exists(drive_path): return

    refresh = False
    while True:
        results = audit_disk(drive_path, catalog, mirror_cache, force_refresh=refresh)
        refresh = False
        console.print("\n[bold yellow]Actions:[/bold yellow]")
        console.print("[S] Sync All | [P] Probe Sizes (1KB) | [M] View Link/Debug | [Q] Exit")
        cmd = input("Choice: ").lower()

        if cmd == 'q': break
        elif cmd == 's': refresh = True
        elif cmd == 'p': refresh = True
        elif cmd.isdigit() or cmd == 'm':
            idx = int(input("ID: ")) - 1 if cmd == 'm' else int(cmd) - 1
            if 0 <= idx < len(results):
                res = results[idx]
                debug_info = f"Status: {res['mirror'].get('status')}\n"
                debug_info += f"Last Checked: {res['mirror'].get('last_checked')}\n"
                if res['mirror'].get('url'):
                    debug_info += f"Mirror URL: {res['mirror']['url']}\n"
                if res['item'].get('manual_url'):
                    debug_info += f"Manual URL: {res['item']['manual_url']}\n"
                if res['mirror'].get('attempted_paths'):
                    debug_info += f"Attempted Paths: {', '.join(res['mirror']['attempted_paths'])}\n"
                console.print(Panel(debug_info, title=f"Debug: {res['item']['name']}"))

if __name__ == "__main__":
    main()