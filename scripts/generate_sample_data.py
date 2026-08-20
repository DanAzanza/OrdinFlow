"""Generates sample cake recipe documents (PDFs), copies high-resolution cake images,
creates a multi-page compilation PDF, renders image recipe cards, and provides a sample
OrdinFlow skill YAML for seamless testing.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import fitz  # PyMuPDF

ARTIFACTS_DIR = Path(r"C:\Users\danie\.gemini\antigravity\brain\63e2684d-1f30-43ac-9778-b524dac762aa")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = PROJECT_ROOT / "sample_data"

IMAGES_DIR = SAMPLE_DIR / "images"
RECIPES_PDF_DIR = SAMPLE_DIR / "recipes_pdf"
RECIPES_CARDS_DIR = SAMPLE_DIR / "recipes_scans_and_cards"

RECIPES = [
    {
        "id": "01_Schwarzwaelder_Kirschtorte",
        "title": "Schwarzwälder Kirschtorte",
        "category": "Sahnetorten & Festtagstorten",
        "date": "15.03.2026",
        "author": "Konditormeister Stefan Weber",
        "prep_time": "60 Min",
        "bake_time": "45 Min",
        "temperature": "175 °C",
        "portions": "12 Stücke",
        "difficulty": "Mittel",
        "image_file": "schwarzwaelder_kirschtorte_1787236044862.jpg",
        "ingredients": [
            "6 Eier (Größe M)",
            "200 g feiner Zucker",
            "1 Pck. Bourbon-Vanillezucker",
            "150 g Weizenmehl & 50 g Speisestärke",
            "50 g Kakaopulver (Backkakao)",
            "2 TL Backpulver & 1 Prise Salz",
            "1 Glas Sauerkirschen (350 g Abtropfgewicht)",
            "4 EL Schwarzwälder Kirschwasser",
            "800 ml kalte Schlagsahne",
            "3 Pck. Sahnesteif",
            "100 g Raspelschokolade (Zartbitter)",
        ],
        "steps": [
            "1. Biskuit: Eier trennen, Eiweiß steif schlagen. Eigelb mit Zucker und 3 EL lauwarmem Wasser cremig weiß rühren. Mehl, Stärke, Kakao und Backpulver mischen und unterheben.",
            "2. In einer Springform (26 cm) bei 175 °C Ober-/Unterhitze ca. 30-35 Minuten backen. Vollständig auskühlen lassen und zweimal waagerecht durchschneiden.",
            "3. Kirschen abtropfen lassen (Saft auffangen). Saft mit etwas Stärke aufkochen, Kirschen unterrühren. Böden mit Kirschwasser beträufeln.",
            "4. Sahne mit Sahnesteif steif schlagen. Kirschen und Sahne schichtweise auf den Böden verteilen. Torte rundherum mit Sahne und Schokoraspeln verzieren.",
        ],
        "notes": "Tipp: Für ein intensives Aroma den Biskuitboden bereits am Vortag backen.",
    },
    {
        "id": "02_Marmorkuchen",
        "title": "Klassischer Marmorkuchen",
        "category": "Rührkuchen & Traditionsgebäck",
        "date": "22.04.2026",
        "author": "Bäckerei & Konditorei Bauer",
        "prep_time": "20 Min",
        "bake_time": "55 Min",
        "temperature": "180 °C",
        "portions": "16 Stücke",
        "difficulty": "Einfach",
        "image_file": "marmorkuchen_classic_1787236057362.jpg",
        "ingredients": [
            "250 g weiche Butter",
            "200 g feiner Zucker",
            "1 Pck. Bourbon-Vanillezucker",
            "4 Eier (Größe M)",
            "350 g Weizenmehl (Type 405)",
            "1 Pck. Backpulver & 1 Prise Salz",
            "100 ml Vollmilch",
            "30 g Kakaopulver & 2 EL Zucker",
            "3 EL Milch für den dunklen Teig",
            "Puderzucker zum Bestäuben",
        ],
        "steps": [
            "1. Butter mit Zucker, Vanillezucker und Salz cremig weiß aufschlagen. Eier einzeln nacheinander gründlich unterrühren.",
            "2. Mehl und Backpulver mischen, abwechselnd mit der Milch kurz unter den Teig rühren, bis ein schwer reißender Teig entsteht.",
            "3. Zwei Drittel des Teiges in eine gefettete und bemehlte Gugelhupfform füllen. In das restliche Drittel Kakao, 2 EL Zucker und 3 EL Milch rühren.",
            "4. Den dunklen Teig auf dem hellen Teig verteilen und mit einer Gabel spiralförmig unterziehen. Bei 180 °C ca. 50-55 Min. backen. Mit Puderzucker bestäuben.",
        ],
        "notes": "Klassiker für jede Kaffeetafel. Bleibt in einer Alufolie bis zu 4 Tage saftig.",
    },
    {
        "id": "03_New_York_Cheesecake",
        "title": "New York Cheesecake",
        "category": "Käsekuchen & Desserts",
        "date": "10.05.2026",
        "author": "Chef Pâtissier Laura Lindner",
        "prep_time": "30 Min",
        "bake_time": "60 Min",
        "temperature": "160 °C",
        "portions": "12 Stücke",
        "difficulty": "Mittel",
        "image_file": "creamy_cheesecake_1787236068077.jpg",
        "ingredients": [
            "200 g Vollkorn-Butterkekse",
            "80 g geschmolzene Butter",
            "600 g Doppelrahm-Frischkäse",
            "250 g Magerquark oder Schmand",
            "150 g feiner Zucker",
            "3 Eier & 1 Eigelb (Größe M)",
            "2 EL Speisestärke",
            "1 Bio-Zitrone (Abrieb und Saft)",
            "1 TL Vanilleextrakt",
            "Frische Himbeeren & Minze",
        ],
        "steps": [
            "1. Kekse fein zerbröseln, mit flüssiger Butter mischen und auf den Boden einer Springform (24 cm) festdrücken. 10 Min. kühlen.",
            "2. Frischkäse, Quark, Zucker, Zitronenabrieb, Vanille und Stärke auf niedrigster Stufe glattrühren.",
            "3. Eier einzeln kurz unterrühren. Masse auf den Keksboden gießen.",
            "4. Bei 160 °C Ober-/Unterhitze ca. 60 Minuten backen. Im leicht geöffneten Ofen 1 Stunde langsam abkühlen lassen, dann mind. 4 Stunden kühlen.",
        ],
        "notes": "Geheimnis: Nicht zu schnell rühren, damit keine Luftbläschen entstehen und die Oberfläche glatt bleibt.",
    },
    {
        "id": "04_Apfel_Streuselkuchen",
        "title": "Feiner Apfel-Streuselkuchen",
        "category": "Blechkuchen & Obstkuchen",
        "date": "18.06.2026",
        "author": "Landbäckerei Sonnenhof",
        "prep_time": "35 Min",
        "bake_time": "40 Min",
        "temperature": "190 °C",
        "portions": "20 Stücke",
        "difficulty": "Einfach",
        "image_file": "apfel_streuselkuchen_1787236080736.jpg",
        "ingredients": [
            "1 kg säuerliche Äpfel (z.B. Boskoop / Elstar)",
            "1 TL gemahlener Zimt & 2 EL Zitronensaft",
            "Boden: 300 g Mehl, 150 g Butter, 100 g Zucker, 2 Eier, 1 TL Backpulver",
            "Streusel: 200 g Mehl, 125 g kalte Butter, 100 g Zucker, 1 Pck. Vanillezucker",
            "1 Prise Salz",
        ],
        "steps": [
            "1. Äpfel schälen, vierteln, entkernen und in mundgerechte Stücke schneiden. Mit Zitronensaft und Zimt vermengen.",
            "2. Zutaten für den Knetteig rasch zu einem glatten Teig verarbeiten und auf einem Backblech ausrollen.",
            "3. Die vorbereiteten Apfelstücke gleichmäßig auf dem Teigboden verteilen.",
            "4. Kalte Butterflocken mit Mehl, Zucker und Vanillezucker zu Streuseln verreiben und über den Äpfeln verteilen. Bei 190 °C ca. 35-40 Min. backen.",
        ],
        "notes": "Schmeckt lauwarm mit einer Kugel Vanilleeis oder frischer Schlagsahne hervorragend.",
    },
    {
        "id": "05_Zitronen_Gugelhupf",
        "title": "Saftiger Zitronen-Gugelhupf",
        "category": "Rührkuchen & Feingebäck",
        "date": "02.07.2026",
        "author": "Pâtisserie Meyer & Söhne",
        "prep_time": "25 Min",
        "bake_time": "50 Min",
        "temperature": "175 °C",
        "portions": "14 Stücke",
        "difficulty": "Einfach",
        "image_file": "zitronen_gugelhupf_1787236094856.jpg",
        "ingredients": [
            "250 g weiche Butter",
            "200 g Rohrzucker",
            "4 Bio-Eier (Größe M)",
            "300 g Dinkelmehl (Type 630)",
            "1 Pck. Weinsteinbackpulver & 1 Prise Salz",
            "Abrieb und Saft von 2 Bio-Zitronen",
            "80 ml Milch",
            "Glasur: 200 g Puderzucker & 4 EL Zitronensaft",
            "Kandierte Zitronenscheiben & Rosmarin",
        ],
        "steps": [
            "1. Butter mit Rohrzucker und Zitronenabrieb 5 Minuten schaumig rühren. Eier einzeln gründlich einrühren.",
            "2. Mehl mit Backpulver mischen und abwechselnd mit Milch und 3 EL Zitronensaft unter den Teig rühren.",
            "3. Teig in eine gebutterte Gugelhupfform geben und bei 175 °C ca. 45-50 Min. backen (Stäbchenprobe).",
            "4. Nach dem Stürzen mit restlichem warmen Zitronensaft tränken. Nach dem Abkühlen mit der Zitronenglasur überziehen.",
        ],
        "notes": "Extra fruchtig und aromatisch dank Bio-Zitronenabrieb direkt in der Butter.",
    },
    {
        "id": "06_Wiener_Sachertorte",
        "title": "Original Wiener Sachertorte",
        "category": "Schokoladentorten & Spezialitäten",
        "date": "14.08.2026",
        "author": "Café & Confiserie Imperial",
        "prep_time": "50 Min",
        "bake_time": "50 Min",
        "temperature": "170 °C",
        "portions": "12 Stücke",
        "difficulty": "Anspruchsvoll",
        "image_file": "wiener_sachertorte_1787236109708.jpg",
        "ingredients": [
            "140 g weiche Butter & 110 g Puderzucker",
            "6 Eigelb & 6 Eiweiß",
            "130 g edle Zartbitter-Kuvertüre (min. 60% Kakao)",
            "110 g Kristallzucker",
            "140 g glattes Weizenmehl",
            "200 g hochwertige Marillenmarmelade",
            "Glasur: 200 g Kuvertüre & 150 g Zucker & 125 ml Wasser",
            "Ungesüßte Schlagsahne zum Servieren",
        ],
        "steps": [
            "1. Kuvertüre im Wasserbad schmelzen. Butter mit Puderzucker schaumig rühren, Eigelbe nach und nach unterrühren, flüssige Schokolade zugeben.",
            "2. Eiweiß mit Kristallzucker zu steifem Schnee schlagen. Eischnee und Mehl abwechselnd vorsichtig unter die Schokomasse heben.",
            "3. In einer Springform (24 cm) bei 170 °C 45-50 Min. backen. Vollständig auskühlen lassen.",
            "4. Kuchen waagerecht halbieren. Warme Marillenmarmelade aufstreichen und zusammensetzen. Mit gekochter Schokoladenglasur gleichmäßig überziehen.",
        ],
        "notes": "Traditionell serviert mit einer Portion ungesüßtem Schlagobers und einer Tasse Wiener Melange.",
    },
]


def create_recipe_pdf(recipe: dict, output_path: Path, embed_image_path: Path | None = None) -> None:
    """Creates a beautifully styled A4 PDF recipe document."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Color palette
    c_primary = (0.55, 0.22, 0.15)     # Warm bakery chocolate-brown
    c_accent = (0.85, 0.50, 0.20)      # Warm gold/orange
    c_dark = (0.15, 0.15, 0.15)        # Charcoal body text
    c_light_bg = (0.98, 0.96, 0.93)    # Warm cream background box
    c_border = (0.88, 0.82, 0.75)      # Soft card border
    c_gray = (0.45, 0.45, 0.45)        # Muted gray

    # 1. Header Banner Box
    page.draw_rect(fitz.Rect(35, 30, 560, 95), color=c_primary, fill=c_primary)
    page.insert_text(fitz.Point(50, 58), "ORDINFLOW KONDITOREI & BACKSTUBE", fontsize=11, color=(1, 1, 1), fontname="helv")
    page.insert_text(fitz.Point(50, 82), recipe["title"].upper(), fontsize=18, color=(1, 0.95, 0.85), fontname="helv")

    # 2. Metadata Key-Value Box
    page.draw_rect(fitz.Rect(35, 105, 340, 245), color=c_border, fill=c_light_bg, width=1)

    meta_lines = [
        ("Kategorie:", recipe["category"]),
        ("Ausstellungsdatum:", recipe["date"]),
        ("Konditor / Autor:", recipe["author"]),
        ("Zubereitungszeit:", recipe["prep_time"]),
        ("Backzeit:", recipe["bake_time"]),
        ("Backtemperatur:", recipe["temperature"]),
        ("Portionen:", recipe["portions"]),
        ("Schwierigkeitsgrad:", recipe["difficulty"]),
    ]

    y_pos = 125
    for label, val in meta_lines:
        page.insert_text(fitz.Point(45, y_pos), label, fontsize=9.5, color=c_primary, fontname="helv")
        page.insert_text(fitz.Point(155, y_pos), val, fontsize=9.5, color=c_dark, fontname="helv")
        y_pos += 14.5

    # 3. Embed Cake Photo on the top right
    img_rect = fitz.Rect(355, 105, 560, 245)
    page.draw_rect(img_rect, color=c_border, width=1)
    if embed_image_path and embed_image_path.exists():
        page.insert_image(img_rect, filename=str(embed_image_path))

    # 4. Ingredients Column (Left)
    col1_left = 35
    col1_width = 210
    page.draw_rect(fitz.Rect(col1_left, 260, col1_left + col1_width, 740), color=c_border, fill=(0.99, 0.98, 0.96), width=1)
    page.draw_rect(fitz.Rect(col1_left, 260, col1_left + col1_width, 285), color=c_accent, fill=c_accent)
    page.insert_text(fitz.Point(col1_left + 15, 277), "ZUTATENLISTE", fontsize=11, color=(1, 1, 1), fontname="helv")

    y_ing = 305
    for ing in recipe["ingredients"]:
        page.draw_circle(fitz.Point(col1_left + 15, y_ing - 3), 2, color=c_accent, fill=c_accent)
        ing_rect = fitz.Rect(col1_left + 24, y_ing - 9, col1_left + col1_width - 10, y_ing + 15)
        page.insert_textbox(ing_rect, ing, fontsize=9, color=c_dark, fontname="helv")
        y_ing += 26 if len(ing) > 30 else 18

    # 5. Instructions Column (Right)
    col2_left = 255
    col2_width = 305
    page.draw_rect(fitz.Rect(col2_left, 260, col2_left + col2_width, 740), color=c_border, fill=(1, 1, 1), width=1)
    page.draw_rect(fitz.Rect(col2_left, 260, col2_left + col2_width, 285), color=c_primary, fill=c_primary)
    page.insert_text(fitz.Point(col2_left + 15, 277), "SCHRITT-FÜR-SCHRITT ZUBEREITUNG", fontsize=11, color=(1, 1, 1), fontname="helv")

    y_step = 305
    for step in recipe["steps"]:
        step_rect = fitz.Rect(col2_left + 15, y_step - 8, col2_left + col2_width - 15, y_step + 80)
        page.insert_textbox(step_rect, step, fontsize=9.5, color=c_dark, fontname="helv")
        y_step += max(60.0, len(step) * 0.42 + 25.0)

    # 6. Recipe Note Box
    note_rect = fitz.Rect(col2_left + 15, 675, col2_left + col2_width - 15, 725)
    page.draw_rect(note_rect, color=c_accent, fill=c_light_bg, width=0.8)
    page.insert_textbox(note_rect + (8, 6, -8, -6), recipe["notes"], fontsize=8.5, color=c_primary, fontname="helv")

    # 7. Signature & Stamp Area at the bottom
    page.draw_line(fitz.Point(35, 755), fitz.Point(560, 755), color=c_border, width=1)
    page.insert_text(fitz.Point(35, 775), "Freigabe & Qualitätsprüfung:", fontsize=9, color=c_gray, fontname="helv")
    page.insert_text(fitz.Point(35, 790), f"Geprüft am: {recipe['date']} in der Backstube", fontsize=8.5, color=c_gray, fontname="helv")

    page.draw_rect(fitz.Rect(360, 762, 555, 805), color=(0.7, 0.7, 0.7), width=0.7)
    page.insert_text(fitz.Point(370, 775), "Unterschrift Konditormeister / Stempel", fontsize=7.5, color=(0.6, 0.6, 0.6), fontname="helv")
    page.insert_text(fitz.Point(390, 795), f"gez. {recipe['author']}", fontsize=9, color=c_primary, fontname="helv")

    # Footer note
    page.insert_text(fitz.Point(35, 825), "OrdinFlow Test-Beispieldokument · 100% On-Premise & Datenschutzkonform generiert", fontsize=7.5, color=(0.6, 0.6, 0.6), fontname="helv")
    page.insert_text(fitz.Point(495, 825), "Dokument: Rezept", fontsize=7.5, color=(0.6, 0.6, 0.6), fontname="helv")

    doc.save(str(output_path))
    doc.close()


def generate_sample_dataset() -> None:
    """Generates all sample assets: images, PDFs, scans, multi-page compilation, and skill config."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    RECIPES_PDF_DIR.mkdir(parents=True, exist_ok=True)
    RECIPES_CARDS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Copy images
    for r in RECIPES:
        src_img = ARTIFACTS_DIR / r["image_file"]
        dest_img = IMAGES_DIR / f"{r['id']}.jpg"
        if src_img.exists():
            shutil.copy2(src_img, dest_img)
            print(f"Copied cake image -> {dest_img.name}")
        else:
            print(f"Warning: source image {src_img} not found")

    # 2. Generate Single-Page PDFs & Image Scans
    for r in RECIPES:
        pdf_path = RECIPES_PDF_DIR / f"Rezept__{r['id']}.pdf"
        img_src = IMAGES_DIR / f"{r['id']}.jpg"
        create_recipe_pdf(r, pdf_path, embed_image_path=img_src)
        print(f"Generated Recipe PDF -> {pdf_path.name}")

        # Render PDF to high-res JPG/PNG recipe card
        doc = fitz.open(str(pdf_path))
        page = doc[0]
        pix = page.get_pixmap(dpi=200)
        card_img_path = RECIPES_CARDS_DIR / f"Rezeptkarte__{r['id']}.jpg"
        pix.save(str(card_img_path))
        doc.close()
        print(f"Rendered Recipe Card Image -> {card_img_path.name}")

    # 3. Generate Multi-Page PDF Compilation
    multipage_pdf_path = RECIPES_PDF_DIR / "Sammelband_Kuchenrezepte_Mehrseitig.pdf"
    multi_doc = fitz.open()
    for r in RECIPES:
        single_pdf = RECIPES_PDF_DIR / f"Rezept__{r['id']}.pdf"
        src_doc = fitz.open(str(single_pdf))
        multi_doc.insert_pdf(src_doc)
        src_doc.close()
    multi_doc.save(str(multipage_pdf_path))
    multi_doc.close()
    print(f"Generated Multi-Page PDF -> {multipage_pdf_path.name} (6 pages)")

    # 4. Generate Recipe Skill Configuration YAML
    skill_yaml_content = """id: import_kuchenrezepte
name: Kuchenrezepte & Konditorei Import
type: import
description: Beispielkonfiguration für automatische Klassifizierung, Datenextraktion und Archivierung von Kuchenrezepten und Kuchenfotos.
enabled: true
allowed_extensions:
- .pdf
- .png
- .jpg
- .jpeg
- .tif
- .tiff
split_multi_documents: true
save_empty_pages: false
trigger: on_queue

document_types:
  Kuchenrezept:
    classification_desc: Ein Backrezept für Kuchen, Torten, Gebäck oder Süßspeisen mit Zutatenliste, Backzeit, Temperatur und Zubereitungsschritten.
    emoji: 🍰
    extraction_fields:
      Rezeptname: Der Name des Rezepts oder Kuchens (z.B. Schwarzwälder Kirschtorte, Marmorkuchen, New York Cheesecake).
      Kategorie: Die Gebäck-Kategorie (z.B. Rührkuchen, Sahnetorten, Blechkuchen, Käsekuchen, Schokoladentorten).
      Backzeit: Die Backzeit in Minuten (z.B. 45 Min, 55 Min).
      Backtemperatur: Die empfohlene Backtemperatur (z.B. 175 °C, 180 °C).
      Portionen: Anzahl der Stücke oder Portionen (z.B. 12 Stücke, 16 Stücke).
      Konditor: Der Name des Autors, Bäckers oder Konditormeisters.
      Datum: Ausstellungs- oder Rezeptdatum im Format DD.MM.YYYY.
      Schwierigkeit: Der Schwierigkeitsgrad (Einfach, Mittel, Anspruchsvoll).
    routing:
      archive: true
      folder_template: Rezepte__{Kategorie}
      filename_template: Rezept__{Rezeptname}__{Backzeit}
    validation:
      optional_fields:
      - Schwierigkeit
      - Portionen
      - Konditor
      signature_required: false

  Kuchenfoto:
    classification_desc: Ein Foto oder Bild eines Kuchens, einer Torte oder eines Gebäcks ohne strukturierten Rezepttext.
    emoji: 📷
    dependent: true
    extraction_fields:
      Beschreibung: Kurze Beschreibung des abgebildeten Kuchens oder Gebäcks (z.B. Schwarzwälder Kirschtorte Anschnitt, Marmorkuchen mit Puderzucker).
    routing:
      archive: true
      folder_template: Fotos__{Beschreibung}
      filename_template: Foto__{Beschreibung}
    validation:
      signature_required: false
"""
    skill_file_path = SAMPLE_DIR / "kuchen_skill_example.yaml"
    skill_file_path.write_text(skill_yaml_content, encoding="utf-8")
    print(f"Generated Skill YAML Template -> {skill_file_path.name}")

    # 5. Generate sample_data/README.md
    readme_content = """# 🍰 OrdinFlow Beispieldaten: Kuchenrezepte & Fotos

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
copy sample_data\\kuchen_skill_example.yaml settings\\skills\\import_kuchenrezepte.yaml
```
Oder lade die Konfiguration über das OrdinFlow Web-Dashboard im Tab **Fähigkeiten (Skills)** hoch.

### 2. Testdateien in den Eingangsordner legen
Kopiere eine oder mehrere Beispieldateien in deinen überwachten Eingangsordner (`watch_dir`, z.B. `C:\\OrdinFlowTest\\Inbox` oder den in `settings/config.yaml` definierten Pfad):
```bash
copy sample_data\\recipes_pdf\\Rezept__01_Schwarzwaelder_Kirschtorte.pdf C:\\OrdinFlowTest\\Inbox\\
copy sample_data\\images\\01_Schwarzwaelder_Kirschtorte.jpg C:\\OrdinFlowTest\\Inbox\\
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
"""
    readme_path = SAMPLE_DIR / "README.md"
    readme_path.write_text(readme_content, encoding="utf-8")
    print(f"Generated sample_data README -> {readme_path.name}")


if __name__ == "__main__":
    generate_sample_dataset()
