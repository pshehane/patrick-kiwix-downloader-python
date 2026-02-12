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
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def run_self_update(dev_mode):
    if dev_mode:
        console.print("[bold cyan]DEV MODE:[/bold cyan] Update check bypassed.")
        return
    try:
        r = requests.get(REPO_RAW_URL, timeout=3, headers=HEADERS)
        if r.status_code == 200:
            with open(sys.argv[0], 'r', encoding='utf-8') as f:
                if f.read() != r.text:
                    with open(sys.argv[0], 'w', encoding='utf-8') as f: f.write(r.text)
                    console.print("[bold green]Script Updated! Launch again.[/bold green]")
                    sys.exit()
    except: pass

def extract_date(filename):
    match = re.search(r"(\d{4}-\d{2})", filename)
    return match.group(1) if match else "0000-00"

def get_mirror_data(dir_path, prefix):
    if dir_path == "MANUAL": return None
    try:
        r = requests.get(f"{MIRROR_BASE}{dir_path}", headers=HEADERS, timeout=8)
        soup = BeautifulSoup(r.text, 'html.parser')
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.endswith('.zim') and href.startswith(prefix):
                size_gb = 0.0
                cols = a.find_parent('tr').find_all('td') if a.find_parent('tr') else []
                for col in cols:
                    text = col.get_text(strip=True).upper()
                    if any(u in text for u in ['G', 'M']):
                        val = float(''.join(c for c in text if c.isdigit() or c == '.'))
                        size_gb = val if 'G' in text else val / 1024
                        break
                links.append({"url": f"{MIRROR_BASE}{dir_path}{href}", "size_gb": size_gb, "date": extract_date(href)})
        links.sort(key=lambda x: x['date'])
        return links[-1] if links else None
    except: return None

def audit_disk(drive_path, catalog):
    table = Table(title="Prep-Disk Command Center v3.2", show_lines=True, show_footer=True)
    table.add_column("ID", justify="center")
    table.add_column("Library", style="cyan", footer="TOTAL")
    table.add_column("Local Ver", justify="center")
    table.add_column("Size (GB)", justify="right", footer="0.0")
    table.add_column("Status", justify="center")

    results = []
    local_files = os.listdir(drive_path)
    total_size = 0.0

    with console.status("[bold yellow]Examining drive and scanning mirrors..."):
        for idx, item in enumerate(catalog['zim_libraries']):
            mirror = get_mirror_data(item['path'], item['prefix'])
            local_match = next((f for f in local_files if f.startswith(item['prefix'])), None)
            
            local_date = extract_date(local_match) if local_match else "N/A"
            local_size = os.path.getsize(os.path.join(drive_path, local_match)) / (2**30) if local_match else 0.0
            total_size += local_size
            
            status = "[red]MISSING[/red]"
            if local_match:
                status = "[green]INSTALLED[/green]"
                if mirror and mirror['date'] > local_date:
                    status = "[bold yellow]OUTDATED[/bold yellow]"
            elif mirror and mirror['size_gb'] > (shutil.disk_usage(drive_path).free / (2**30)):
                status = "[bold red]TOO BIG[/bold red]"
            
            table.add_row(str(idx+1), item['name'], local_date, f"{local_size:.1f}", status)
            results.append({"item": item, "mirror": mirror, "local": local_match, "local_date": local_date})

    table.columns[3].footer = f"{total_size:.1f}"
    console.print(table)
    free_gb = shutil.disk_usage(drive_path).free / (2**30)
    console.print(f"Free Space: [bold green]{free_gb:.1f} GB[/bold green]")
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
    run_self_update(args.dev)
    
    try:
        with open('catalog.json', 'r') as f: catalog = json.load(f)
    except: console.print("[red]Error: catalog.json missing![/red]"); return

    drive_l = input("Enter Drive Letter: ").upper()
    drive_path = f"{drive_l}:\\"
    if not os.path.exists(drive_path): return

    while True:
        results, free_gb = audit_disk(drive_path, catalog)
        console.print("\n[R] Recommended Set | [U] Update Outdated | [A] App Installers | [M] Manual ID | [Q] Exit")
        cmd = input("Choice: ").lower()

        if cmd == 'q': break
        if cmd == 'r':
            for r in results:
                if r['item']['rec'] and not r['local'] and r['mirror'] and r['mirror']['size_gb'] < free_gb:
                    download_file(r['mirror']['url'], os.path.join(drive_path, r['mirror']['url'].split('/')[-1]))
        if cmd == 'u':
            for r in results:
                if "OUTDATED" in r['local']: # Placeholder logic
                    os.remove(os.path.join(drive_path, r['local']))
                    download_file(r['mirror']['url'], os.path.join(drive_path, r['mirror']['url'].split('/')[-1]))
        if cmd == 'a':
            for sw in catalog['software']:
                download_file(sw['url'], os.path.join(drive_path, sw['filename']))
        if cmd == 'm' or cmd.isdigit():
            idx = int(input("Enter ID: ")) - 1 if cmd == 'm' else int(cmd) - 1
            target = results[idx]
            if target['item']['path'] == "MANUAL":
                console.print(Panel(f"Manual URL:\n{target['item']['manual_url']}"))
            elif target['mirror']:
                download_file(target['mirror']['url'], os.path.join(drive_path, target['mirror']['url'].split('/')[-1]))
        if cmd == '5': # Cloning logic
             shutil.copy2(sys.argv[0], os.path.join(drive_path, "prepper-downloader.py"))

if __name__ == "__main__":
    main()