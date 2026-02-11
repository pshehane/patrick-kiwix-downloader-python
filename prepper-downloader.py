import os
import requests
import shutil
from bs4 import BeautifulSoup
from tqdm import tqdm
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

# --- CONFIG ---
MIRROR_BASE = "https://ftp.fau.de/kiwix/zim/"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# Priority Catalog
PRIORITIZED_CATALOG = [
    {"name": "Wikipedia (EN Maxi)", "path": "wikipedia/", "search_terms": ["wikipedia_en_all_maxi"]},
    {"name": "WikiMed (Medical)", "path": "wikipedia/", "search_terms": ["wikimed_en_all", "wikipedia_en_medicine"]},
    {"name": "iFixit (Repair)", "path": "ifixit/", "search_terms": ["ifixit_en_all"]},
    {"name": "LibreTexts (Science)", "path": "libretexts/", "search_terms": ["libretexts_en_all"]},
    {"name": "Sustainability SE", "path": "stack_exchange/", "search_terms": ["sustainableliving"]},
    {"name": "WikiVoyage (Travel)", "path": "wikivoyage/", "search_terms": ["wikivoyage_en_all"]},
    {"name": "Project Gutenberg (Books)", "path": "gutenberg/", "search_terms": ["gutenberg_en_all"]}
]

def get_latest_url_and_size(dir_path, search_terms):
    try:
        r = requests.get(f"{MIRROR_BASE}{dir_path}", headers=HEADERS, timeout=10)
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
    r = requests.get(url, stream=True, headers=HEADERS)
    total = int(r.headers.get('content-length', 0))
    if total < 1000: return False
    with tqdm(total=total, unit='iB', unit_scale=True, desc=os.path.basename(dest)) as pbar:
        with open(dest, 'wb') as f:
            for chunk in r.iter_content(chunk_size=1024*1024):
                f.write(chunk)
                pbar.update(len(chunk))
    return True

def audit_disk(drive_path):
    table = Table(title="[bold]Current Files on Disk[/bold]", show_lines=True)
    table.add_column("File Name", style="cyan")
    table.add_column("Size (GB)", justify="right")
    
    files = [f for f in os.listdir(drive_path) if f.endswith(('.zim', '.apk', '.exe', '.dmg', '.txt'))]
    for f in sorted(files):
        size = os.path.getsize(os.path.join(drive_path, f)) / (2**30)
        table.add_row(f, f"{size:.2f}")
    
    console.print(table)
    total, used, free = shutil.disk_usage(drive_path)
    console.print(f"Total Disk: {total/(2**30):.1f}GB | [bold green]Free: {free/(2**30):.1f}GB[/bold green]")
    return free / (2**30)

def create_emergency_readme(drive_path):
    content = """# EMERGENCY INSTRUCTIONS: OFFLINE KNOWLEDGE BASE
1. ANDROID: Install the .apk file on this drive. In Kiwix settings, select this USB drive as the 'Storage Folder'.
2. iOS: Use the 'Files' app to open .zim files in the Kiwix app.
3. PC/MAC: Use Kiwix Desktop to open the .zim files directly. (Installers included in /Software)
"""
    readme_path = os.path.join(drive_path, "!!!_README_FIRST_!!!.txt")
    with open(readme_path, "w") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno()) # Fixed: Moved inside the with block

def main():
    console.print(Panel.fit("PREP-DISK COMMAND CENTER v2.2", style="bold green"))
    drive_l = input("Enter drive letter (e.g., F): ").upper()
    drive_path = f"{drive_l}:\\"

    if not os.path.exists(drive_path):
        console.print("[red]Drive not found.[/red]")
        return

    while True:
        console.print("\n" + "="*40)
        free_gb = audit_disk(drive_path)
        
        console.print("\n[bold yellow]Main Menu:[/bold yellow]")
        console.print("1. [cyan]Sync/Update Knowledge[/cyan]")
        console.print("2. [red]Delete a file[/red]")
        console.print("3. [green]Download Android APK Installer[/green]")
        console.print("4. [blue]Download PC/Mac Desktop Apps[/blue]")
        console.print("5. [magenta]Generate README[/magenta]")
        console.print("Q. [white]Safe Eject & Exit[/white]")
        
        choice = input("\nSelect: ").lower()

        if choice in ['q', 'x', 'exit']:
            create_emergency_readme(drive_path)
            console.print("[bold green]Buffers flushed. Disk ready for off-grid use.[/bold green]")
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

            if queue and input(f"Download {len(queue)} items ({projected:.1f} GB)? (y/n): ").lower() == 'y':
                for item in queue:
                    download_file(item['url'], os.path.join(drive_path, item['url'].split('/')[-1]))

        elif choice == "2":
            fn = input("Enter partial filename to delete: ")
            for f in os.listdir(drive_path):
                if fn in f:
                    if input(f"Delete {f}? (y/n): ").lower() == 'y':
                        os.remove(os.path.join(drive_path, f))

        elif choice == "3":
            url = "https://download.kiwix.org/release/kiwix-android/kiwix-android-3.11.0-standalone.apk"
            download_file(url, os.path.join(drive_path, "INSTALL_Kiwix_Android_Standalone.apk"))

        elif choice == "4":
            win_url = "https://download.kiwix.org/release/kiwix-desktop/kiwix-desktop_windows_x64.zip"
            mac_url = "https://download.kiwix.org/release/kiwix-desktop/kiwix-desktop_macos_x64.dmg"
            download_file(win_url, os.path.join(drive_path, "Kiwix_Desktop_Windows.zip"))
            download_file(mac_url, os.path.join(drive_path, "Kiwix_Desktop_Mac.dmg"))

        elif choice == "5":
            create_emergency_readme(drive_path)
            console.print("[green]README updated.[/green]")

if __name__ == "__main__":
    main()