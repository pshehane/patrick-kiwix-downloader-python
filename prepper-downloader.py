import os
import requests
import shutil
import sys
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

# Survival Catalog
PRIORITIZED_CATALOG = [
    {"name": "Wikipedia (EN Maxi)", "path": "wikipedia/", "search_terms": ["wikipedia_en_all_maxi"]},
    {"name": "WikiMed (Medical)", "path": "wikipedia/", "search_terms": ["wikimed_en_all", "wikipedia_en_medicine"]},
    {"name": "iFixit (Repair)", "path": "ifixit/", "search_terms": ["ifixit_en_all"]},
    {"name": "LibreTexts (Science)", "path": "libretexts/", "search_terms": ["libretexts_en_all"]},
    {"name": "Sustainability SE", "path": "stack_exchange/", "search_terms": ["sustainableliving"]},
    {"name": "WikiVoyage (Travel)", "path": "wikivoyage/", "search_terms": ["wikivoyage_en_all"]},
    {"name": "Project Gutenberg (Books)", "path": "gutenberg/", "search_terms": ["gutenberg_en_all"]}
]

def run_self_update():
    """Checks GitHub for a newer version of the script. Skips if offline."""
    console.print("[dim yellow]Checking for script updates...[/dim yellow]")
    try:
        r = requests.get(REPO_RAW_URL, timeout=3, headers=HEADERS)
        if r.status_code == 200:
            current_script = sys.argv[0]
            with open(current_script, 'r', encoding='utf-8') as f:
                local_content = f.read()
            
            if r.text != local_content:
                with open(current_script, 'w', encoding='utf-8') as f:
                    f.write(r.text)
                console.print(Panel("[bold green]Script Updated Successfully![/bold green]\nPlease launch the script again to use the latest version."))
                sys.exit()
    except (requests.exceptions.RequestException, Exception):
        console.print("[dim red]Offline or GitHub unreachable. Skipping update.[/dim red]")

def get_latest_url_and_size(dir_path, search_terms):
    try:
        r = requests.get(f"{MIRROR_BASE}{dir_path}", headers=HEADERS, timeout=8)
        soup = BeautifulSoup(r.text, 'html.parser')
        links = []
        for a in soup.find_all('a', href=True):
            if a['href'].endswith('.zim') and any(t in a['href'] for t in search_terms):
                size_gb = 0.1
                row = a.find_parent('tr')
                if row:
                    cols = row.find_all('td')
                    if len(cols) >= 4:
                        size_text = cols[3].get_text(strip=True)
                        val = float(''.join(c for c in size_text if c.isdigit() or c == '.'))
                        size_gb = val if 'G' in size_text else val / 1024
                links.append({"url": f"{MIRROR_BASE}{dir_path}{a['href']}", "size_gb": size_gb})
        if not links: return None
        links.sort(key=lambda x: x['url'])
        return links[-1]
    except: return None

def download_file(url, dest):
    try:
        r = requests.get(url, stream=True, headers=HEADERS)
        total = int(r.headers.get('content-length', 0))
        if total < 1000: return False
        with tqdm(total=total, unit='iB', unit_scale=True, desc=os.path.basename(dest)) as pbar:
            with open(dest, 'wb') as f:
                for chunk in r.iter_content(chunk_size=1024*1024):
                    f.write(chunk)
                    pbar.update(len(chunk))
        return True
    except: return False

def audit_disk(drive_path):
    table = Table(title="[bold]Drive Audit[/bold]", show_lines=True)
    table.add_column("File Name", style="cyan")
    table.add_column("Size (GB)", justify="right")
    
    files = [f for f in os.listdir(drive_path) if f.endswith(('.zim', '.apk', '.exe', '.dmg', '.txt', '.py'))]
    for f in sorted(files):
        size = os.path.getsize(os.path.join(drive_path, f)) / (2**30)
        table.add_row(f, f"{size:.2f}")
    
    console.print(table)
    total, used, free = shutil.disk_usage(drive_path)
    console.print(f"Drive: {drive_path} | [bold green]Free: {free/(2**30):.1f}GB[/bold green]")
    return free / (2**30)

def create_emergency_readme(drive_path):
    content = """# EMERGENCY INSTRUCTIONS: OFFLINE KNOWLEDGE BASE
1. ANDROID: Install 'INSTALL_Kiwix_Android_Standalone.apk'. In Kiwix settings, point to this drive.
2. iOS: Open .zim files via the 'Files' app using the Kiwix app.
3. PC/MAC: Installers included. Use them to open .zim files directly.
4. UPDATER: Run 'prepper-downloader.py' (requires Python) to update this drive.
"""
    readme_path = os.path.join(drive_path, "!!!_README_FIRST_!!!.txt")
    with open(readme_path, "w") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())

def main():
    # --- AUTO UPDATE ON START ---
    run_self_update()
    
    console.print(Panel.fit("PREP-DISK MASTER CONTROLLER v2.3", style="bold green"))
    drive_l = input("Enter target drive letter (e.g., F): ").upper()
    drive_path = f"{drive_l}:\\"

    if not os.path.exists(drive_path):
        console.print("[red]Drive not found.[/red]")
        return

    while True:
        console.print("\n" + "="*40)
        free_gb = audit_disk(drive_path)
        
        console.print("\n[bold yellow]Actions:[/bold yellow]")
        console.print("1. [cyan]Sync Survival Knowledge[/cyan]")
        console.print("2. [red]Delete Files[/red]")
        console.print("3. [green]Download App Installers[/green] (Mobile & Desktop)")
        console.print("4. [magenta]Install Updater Script to Drive[/magenta]")
        console.print("Q. [white]Safe Eject & Exit[/white]")
        
        choice = input("\nSelect: ").lower()

        if choice in ['q', 'x']:
            create_emergency_readme(drive_path)
            console.print("[bold green]System Optimized. Safe to Eject.[/bold green]")
            break

        elif choice == "1":
            queue = []
            projected = 0
            with console.status("[yellow]Checking mirrors..."):
                for item in PRIORITIZED_CATALOG:
                    data = get_latest_url_and_size(item['path'], item['search_terms'])
                    if not data: continue
                    fname = data['url'].split('/')[-1]
                    if not os.path.exists(os.path.join(drive_path, fname)) and (projected + data['size_gb']) < free_gb:
                        queue.append(data)
                        projected += data['size_gb']

            if queue and input(f"Sync {len(queue)} items ({projected:.1f} GB)? (y/n): ").lower() == 'y':
                for item in queue:
                    download_file(item['url'], os.path.join(drive_path, item['url'].split('/')[-1]))

        elif choice == "2":
            fn = input("Partial name to delete: ")
            for f in os.listdir(drive_path):
                if fn in f and input(f"Delete {f}? (y/n): ").lower() == 'y':
                    os.remove(os.path.join(drive_path, f))

        elif choice == "3":
            urls = {
                "Android": "https://download.kiwix.org/release/kiwix-android/kiwix-android-3.11.0-standalone.apk",
                "Windows": "https://download.kiwix.org/release/kiwix-desktop/kiwix-desktop_windows_x64.zip",
                "Mac": "https://download.kiwix.org/release/kiwix-desktop/kiwix-desktop_macos_x64.dmg"
            }
            for platform, url in urls.items():
                console.print(f"[yellow]Downloading {platform} installer...[/yellow]")
                download_file(url, os.path.join(drive_path, os.path.basename(url)))

        elif choice == "4":
            # Copy the current script to the drive for portability
            target_script = os.path.join(drive_path, "prepper-downloader.py")
            shutil.copy2(sys.argv[0], target_script)
            console.print(f"[bold green]Updater script cloned to {target_script}[/bold green]")

if __name__ == "__main__":
    main()