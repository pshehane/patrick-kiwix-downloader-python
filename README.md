# Patrick's Prep-Disk Downloader

An automated, developer-focused management tool for building a high-capacity, off-grid knowledge base. This script automates the retrieval of compressed ZIM archives from the Kiwix library, ensuring you have a survival toolkit on a thumb drive.

## 🚀 Features
- **Smart Bucket Logic:** Dynamically calculates available disk space and prioritizes "Survival Critical" knowledge (Wikipedia, Medical, Repair).
- **Dynamic Mirror Scraper:** Avoids broken 'latest' links by deep-scanning academic mirrors (FAU) for the most recent date-stamped archives.
- **Resilience Seed:** Automatically downloads standalone Android APKs and Desktop installers (Win/Mac) for off-grid setup.
- **Persistent Management Shell:** Audit, delete, and sync files in a single session.
- **Emergency Preparedness:** Generates a README for non-technical users to access the data in an emergency.

## 🛠 Prerequisites
- **Python:** 3.10+
- **Storage:** 256GB to 2TB External Drive (Formatted as **exFAT** for cross-platform compatibility).

### Dependencies
Install the required libraries via pip:
```bash
pip install requests beautifulsoup4 tqdm rich