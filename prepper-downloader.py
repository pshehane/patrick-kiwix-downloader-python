import os, requests, shutil, sys, json, re
from tqdm import tqdm
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

console = Console()

# --- CONFIG ---
CATALOG_FILE = "zim_full_catalog.json"
MANIFEST_FILE = "additional_titles.json"
CACHE_FILE = "mirror_cache.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def load_json(filename):
    if not os.path.exists(filename): return {}
    with open(filename, 'r', encoding='utf-8') as f: return json.load(f)

def extract_date(filename):
    match = re.search(r"(\d{4}-\d{2})", filename)
    return match.group(1) if match else "N/A"

class PrepManager:
    def __init__(self, drive_path):
        self.drive_path = drive_path
        self.catalog = load_json(CATALOG_FILE)
        self.manifest = load_json(MANIFEST_FILE).get("exhaustive_survival_manifest", {})
        self.mirror_cache = load_json(CACHE_FILE)
        
    def audit(self):
        table = Table(title="Prep-Disk V2 Command Center", show_lines=True, show_footer=True)
        table.add_column("ID", justify="center")
        table.add_column("Library", style="cyan", footer="TOTALS")
        table.add_column("Local Ver", justify="center")
        table.add_column("Mirror Ver", justify="center")
        table.add_column("Local GB", justify="right")
        table.add_column("Mirror GB", justify="right")
        table.add_column("Status", justify="center")

        local_files = os.listdir(self.drive_path)
        sum_l, sum_m = 0.0, 0.0
        _, _, free = shutil.disk_usage(self.drive_path)
        self.free_gb = free / (2**30)

        self.results = []
        # We flatten the manifest for the main table view
        flattened_list = []
        for tier, titles in self.manifest.items():
            for title in titles:
                flattened_list.append((tier, title))

        for idx, (tier, prefix) in enumerate(flattened_list):
            # Look up mirror data from the crawled catalog
            mirror = self.catalog.get("libraries", {}).get(prefix, {})
            local_match = next((f for f in local_files if f.startswith(prefix)), None)
            
            l_ver = extract_date(local_match) if local_match else "N/A"
            m_ver = mirror.get('date', "N/A")
            l_gb = os.path.getsize(os.path.join(self.drive_path, local_match)) / (2**30) if local_match else 0.0
            m_gb = mirror.get('size_gb', 0.0) if mirror else 0.0
            
            sum_l += l_gb
            sum_m += m_gb
            
            status = "[red]Missing[/red]"
            if not mirror: status = "[dim]Unknown/Not in Catalog[/dim]"
            elif local_match:
                status = "[green]Installed[/green]"
                if m_ver > l_ver: status = "[bold yellow]Update Avail[/bold yellow]"
            elif m_gb > self.free_gb: status = "[bold red]Too Big[/bold red]"
            
            table.add_row(str(idx+1), prefix, l_ver, m_ver, f"{l_gb:.1f}", f"{m_gb:.1f}", status)
            self.results.append({"prefix": prefix, "mirror": mirror, "local": local_match, "l_ver": l_ver, "m_ver": m_ver, "m_gb": m_gb, "tier": tier})

        table.columns[4].footer = f"{sum_l:.1f}"
        table.columns[5].footer = f"{sum_m:.1f}"
        console.print(table)
        console.print(f"Drive Free Space: [bold green]{self.free_gb:.1f} GB[/bold green]")

    def download(self, url, dest):
        try:
            r = requests.get(url, stream=True, headers=HEADERS)
            total = int(r.headers.get('content-length', 0))
            with tqdm(total=total, unit='iB', unit_scale=True, desc=os.path.basename(dest)) as pbar:
                with open(dest, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024*1024):
                        f.write(chunk); pbar.update(len(chunk))
            return True
        except: return False

    def recommend(self):
        rec_list = []
        temp_free = self.free_gb
        # Sort manifest tiers numerically
        sorted_tiers = sorted(self.manifest.keys())
        
        for tier in sorted_tiers:
            for prefix in self.manifest[tier]:
                mirror = self.catalog.get("libraries", {}).get(prefix)
                # Check if mirror exists and has a valid URL
                if mirror and mirror.get('url'):
                    # Safe retrieval of size_gb with a default of 0.0
                    m_size = mirror.get('size_gb', 0.0)
                    
                    # Check if not installed and fits
                    if not any(f.startswith(prefix) for f in os.listdir(self.drive_path)):
                        if m_size < temp_free:
                            rec_list.append(mirror)
                            temp_free -= m_size
                                    
        if not rec_list:
            console.print("[yellow]Nothing to recommend (No space or all items installed).[/yellow]")
        else:
            console.print(Panel("\n".join([f"• {m['filename']} ({m.get('size_gb', 0.0):.1f} GB)" for m in rec_list]), title="Manifest Recommendations"))
            if Confirm.ask("Download recommended queue?"):
                for m in rec_list:
                    self.download(m['url'], os.path.join(self.drive_path, m['filename']))

    def manual_tier_picker(self):
        tiers = sorted(self.manifest.keys())
        for i, t in enumerate(tiers): console.print(f"{i+1}. {t}")
        t_idx = int(Prompt.ask("Select Priority Tier")) - 1
        selected_tier = tiers[t_idx]
        
        tier_items = []
        for prefix in self.manifest[selected_tier]:
            mirror = self.catalog.get("libraries", {}).get(prefix)
            tier_items.append((prefix, mirror))
            
        pick_table = Table(title=f"Manual Picker: {selected_tier}")
        pick_table.add_column("ID")
        pick_table.add_column("Library")
        pick_table.add_column("Size")
        for i, (pre, mir) in enumerate(tier_items):
            size = f"{mir['size_gb']:.1f} GB" if mir else "N/A"
            pick_table.add_row(str(i+1), pre, size)
        console.print(pick_table)
        
        choice = int(Prompt.ask("ID to download")) - 1
        target_mir = tier_items[choice][1]
        if target_mir:
            self.download(target_mir['url'], os.path.join(self.drive_path, target_mir['filename']))

def main():
    drive_l = Prompt.ask("Enter Drive Letter").upper()
    drive_path = f"{drive_l}:\\"
    if not os.path.exists(drive_path): return

    mgr = PrepManager(drive_path)
    
    while True:
        mgr.audit()
        console.print("\n[bold yellow]V2 Menus:[/bold yellow]")
        console.print("[R] Recommended (Auto-fill by Priority) | [P] Priority Tier Manual Picker")
        console.print("[D] Delete Item | [Q] Exit")
        
        cmd = input("\nAction: ").lower()
        if cmd == 'q': break
        elif cmd == 'r': mgr.recommend()
        elif cmd == 'p': mgr.manual_tier_picker()
        elif cmd == 'd':
            idx = int(Prompt.ask("ID to Delete")) - 1
            os.remove(os.path.join(mgr.drive_path, mgr.results[idx]['local']))

if __name__ == "__main__":
    main()