# 🍰 OrdinFlow Beispieldaten: Kuchenrezepte & Fotos

Dieses Verzeichnis enthält sofort einsatzbereite Beispieldaten, mit denen die Funktionen von **OrdinFlow** (Dokumentenklassifizierung, OCR & VLM-Extraktion, Bilderkennung, Multi-Page-Splitting und Routing) direkt getestet werden können.

---

## 📂 Struktur der Beispieldaten

```
sample_data/
├── images/                         # 6 hochauflösende KI-generierte Kuchenfotos (.jpg)
│   ├── 01_Schwarzwaelder_Kirschtorte.jpg
│   ├── 02_Marmorkuchen.jpg
│   ├── 03_New_York_Cheesecake.jpg
│   ├── 04_Apfel_Streuselkuchen.jpg
│   ├── 05_Zitronen_Gugelhupf.jpg
│   └── 06_Wiener_Sachertorte.jpg
│
├── recipes_pdf/                    # Formatierte DIN-A4 PDF-Rezeptdokumente
│   ├── Rezept__01_Schwarzwaelder_Kirschtorte.pdf
│   ├── Rezept__02_Marmorkuchen.pdf
│   ├── Rezept__03_New_York_Cheesecake.pdf
│   ├── Rezept__04_Apfel_Streuselkuchen.pdf
│   ├── Rezept__05_Zitronen_Gugelhupf.pdf
│   ├── Rezept__06_Wiener_Sachertorte.pdf
│   └── Sammelband_Kuchenrezepte_Mehrseitig.pdf  # 6-seitiges PDF zum Testen des Multi-Page-Splittings
│
├── recipes_scans_and_cards/        # Gerenderte Rezeptkarten als Bilddateien (.jpg) für Bild-OCR & Vision
│   ├── Rezeptkarte__01_Schwarzwaelder_Kirschtorte.jpg
│   ├── Rezeptkarte__02_Marmorkuchen.jpg
│   ├── ...
│
└── kuchen_skill_example.yaml       # Fertig konfigurierter Skill für Kuchenrezepte & Kuchenfotos
```

---

## 🚀 Schnellstart: So testest du OrdinFlow mit diesen Beispieldaten

### 1. Kuchen-Skill aktivieren (Optional für angepasstes Routing)
Kopiere `sample_data/kuchen_skill_example.yaml` in deinen Skill-Ordner:
```bash
copy sample_data\kuchen_skill_example.yaml settings\skills\import_kuchenrezepte.yaml
```
Oder lade die Konfiguration über das OrdinFlow Web-Dashboard im Tab **Fähigkeiten (Skills)** hoch.

### 2. Testdateien in den Eingangsordner legen
Kopiere eine oder mehrere Beispieldateien in deinen überwachten Eingangsordner (`watch_dir`, z.B. `C:\OrdinFlowTest\Inbox` oder den in `settings/config.yaml` definierten Pfad):
```bash
copy sample_data\recipes_pdf\Rezept__01_Schwarzwaelder_Kirschtorte.pdf C:\OrdinFlowTest\Inbox\
copy sample_data\images\01_Schwarzwaelder_Kirschtorte.jpg C:\OrdinFlowTest\Inbox\
```

### 3. Was passiert automatisch?
1. **Erkennung & Klassifizierung:** OrdinFlow erkennt automatisch, ob es sich um ein `Kuchenrezept` (strukturiertes Dokument) oder ein `Kuchenfoto` handelt.
2. **Datenextraktion:**
   - `Rezeptname` (z.B. "Schwarzwälder Kirschtorte")
   - `Kategorie` (z.B. "Sahnetorten & Festtagstorten")
   - `Backzeit` (z.B. "45 Min")
   - `Backtemperatur` (z.B. "175 °C")
   - `Portionen` (z.B. "12 Stücke")
   - `Konditor / Autor` (z.B. "Konditormeister Stefan Weber")
   - `Datum` (z.B. "15.03.2026")
3. **Automatisches Routing:** Die Datei wird automatisch nach `Target/Rezepte__<Kategorie>/Rezept__<Rezeptname>__<Backzeit>.pdf` verschoben und mit einer `.meta` JSON-Sidecar-Datei versehen.
4. **Mehrseitige PDFs:** Das Dokument `Sammelband_Kuchenrezepte_Mehrseitig.pdf` demonstriert das automatische Trennen (`split_multi_documents: true`) in einzelne Rezepte.
