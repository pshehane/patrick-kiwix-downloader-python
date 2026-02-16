import os, requests, shutil, sys, json, re, argparse
from bs4 import BeautifulSoup
from tqdm import tqdm
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm

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
    with open(filename, 'w', encoding='utf-8') as f: json.dump(data, f, indent=2)

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
    """Deep search for latest ZIM version."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    if dir_path == "MANUAL": return {"status": "MANUAL", "last_checked": timestamp}
    
    search_paths = [dir_path, "wikipedia/", "other/", "stack_exchange/", ""]
    for path in search_paths:
        try:
            r = requests.get(f"{MIRROR_BASE}{path}", headers=HEADERS, timeout=10)
            if r.status_code != 200: continue
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
                    links.append({"url": f"{MIRROR_BASE}{path}{href}", "size_gb": size_gb, "date": extract_date(href)})
            if links:
                links.sort(key=lambda x: x['date'])
                latest = links[-1]
                if probe and latest['size_gb'] == 0:
                    latest['size_gb'] = probe_mirror_size(latest['url'])
                latest.update({"status": "SUCCESS", "last_checked": timestamp})
                return latest
        except: continue
    return {"status": "NOT_FOUND", "last_checked": timestamp, "size_gb": 0.0}

def audit_system(drive_path, catalog, mirror_cache, force_refresh=False):
    table = Table(title="Prep-Disk Console v4.0", show_lines=True, show_footer=True)
    table.add_column("ID", justify="center")
    table.add_column("Library", style="cyan", footer="TOTALS")
    table.add_column("Local Ver", justify="center")
    table.add_column("Update Ver", justify="center")
    table.add_column("Local GB", justify="right")
    table.add_column("Mirror GB", justify="right")
    table.add_column("Status", justify="center")

    results = []
    local_files = os.listdir(drive_path)
    sum_l, sum_m = 0.0, 0.0
    _, _, free = shutil.disk_usage(drive_path)
    free_gb = free / (2**30)

    # Status indicator only if we are actually hitting the network
    status_msg = "[bold yellow]Refreshing Mirror Cache..." if force_refresh else "[bold blue]Loading Cache..."
    with console.status(status_msg):
        for idx, item in enumerate(catalog['zim_libraries']):
            if force_refresh or item['prefix'] not in mirror_cache:
                mirror_cache[item['prefix']] = get_mirror_data(item['path'], item['prefix'], probe=force_refresh)
            
            mirror = mirror_cache[item['prefix']]
            local_match = next((f for f in local_files if f.startswith(item['prefix'])), None)
            
            l_ver = extract_date(local_match) if local_match else "N/A"
            m_ver = mirror.get('date', "N/A")
            l_gb = os.path.getsize(os.path.join(drive_path, local_match)) / (2**30) if local_match else 0.0
            m_gb = mirror.get('size_gb', 0.0)
            
            sum_l += l_gb
            sum_m += m_gb
            
            # 2026 Status Logic
            status = "[red]Not Installed[/red]"
            if mirror.get('status') != "SUCCESS" and mirror.get('status') != "MANUAL":
                status = f"[dim red]Not Found ({mirror.get('status')})[/dim red]"
            elif local_match:
                status = "[green]Installed[/green]"
                if mirror.get('status') == "SUCCESS" and m_ver > l_ver:
                    status = "[bold yellow]Update Available[/bold yellow]"
            elif m_gb > free_gb:
                status = "[bold red]Too Big[/bold red]"
            
            table.add_row(str(idx+1), item['name'], l_ver, m_ver, f"{l_gb:.1f}", f"{m_gb:.1f}", status)
            results.append({"item": item, "mirror": mirror, "local": local_match, "l_ver": l_ver, "m_ver": m_ver, "l_gb": l_gb, "m_gb": m_gb})

    table.columns[4].footer = f"{sum_l:.1f}"
    table.columns[5].footer = f"{sum_m:.1f}"
    console.print(table)
    console.print(f"Drive Free Space: [bold green]{free_gb:.1f} GB[/bold green]")
    save_json(CACHE_FILE, mirror_cache)
    return results, free_gb

def download_file(url, dest):
    r = requests.get(url, stream=True, headers=HEADERS)
    total = int(r.headers.get('content-length', 0))
    with tqdm(total=total, unit='iB', unit_scale=True, desc=os.path.basename(dest)) as pbar:
        with open(dest, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024*1024):
                f.write(chunk); pbar.update(len(chunk))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dev", action="store_true")
    args, _ = parser.parse_known_args()
    
    catalog = load_json('catalog.json')
    mirror_cache = load_json(CACHE_FILE)
    
    drive_l = input("Enter Drive Letter (e.g., F): ").upper()
    drive_path = f"{drive_l}:\\"
    if not os.path.exists(drive_path): return

    refresh = False
    while True:
        results, free_gb = audit_system(drive_path, catalog, mirror_cache, force_refresh=refresh)
        refresh = False
        
        console.print("\n[bold yellow]Menu Options:[/bold yellow]")
        console.print("[P] Probe/Sync Mirror | [R] Make Recommendation | [M] View/Debug Item")
        console.print("[ID] Update Specific Item | [D] Delete Item | [Q] Exit")
        cmd = input("\nAction: ").lower()

        if cmd == 'q': break
        elif cmd == 'p': refresh = True
        elif cmd == 'r':
            rec_list = []
            proj_space = free_gb
            for r in results:
                if not r['local'] and r['mirror'].get('status') == "SUCCESS" and r['m_gb'] < proj_space:
                    if r['item'].get('rec', True):
                        rec_list.append(r)
                        proj_space -= r['m_gb']
            
            if not rec_list:
                console.print("[yellow]No recommendations possible for current space.[/yellow]")
            else:
                console.print(Panel("\n".join([f"• {x['item']['name']} ({x['m_gb']:.1f} GB)" for x in rec_list]), title="Recommended for Download"))
                if Confirm.ask("Proceed with these downloads?"):
                    for x in rec_list: download_file(x['mirror']['url'], os.path.join(drive_path, x['mirror']['url'].split('/')[-1]))

        elif cmd.isdigit():
            idx = int(cmd) - 1
            if 0 <= idx < len(results):
                target = results[idx]
                if target['local'] and Confirm.ask(f"Replace old {target['l_ver']} with {target['m_ver']}?"):
                    os.remove(os.path.join(drive_path, target['local']))
                    download_file(target['mirror']['url'], os.path.join(drive_path, target['mirror']['url'].split('/')[-1]))
                elif not target['local'] and target['mirror'].get('status') == "SUCCESS":
                    download_file(target['mirror']['url'], os.path.join(drive_path, target['mirror']['url'].split('/')[-1]))

        elif cmd == 'd':
            idx = int(input("ID to Delete: ")) - 1
            if results[idx]['local']:
                if Confirm.ask(f"Permanently delete {results[idx]['local']}?"):
                    os.remove(os.path.join(drive_path, results[idx]['local']))

        elif cmd == 'm':
            idx = int(input("ID to Debug: ")) - 1
            res = results[idx]
            console.print(Panel(f"Mirror Status: {res['mirror'].get('status')}\nPath: {res['mirror'].get('url', 'N/A')}\nChecked: {res['mirror'].get('last_checked')}", title=res['item']['name']))

if __name__ == "__main__":
    main()