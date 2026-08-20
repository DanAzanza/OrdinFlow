"""Generates sample cake recipe documents (PDFs), copies high-resolution cake images,
creates a multi-page compilation PDF, renders image recipe cards, and provides a sample
OrdinFlow skill YAML in English for seamless testing and demonstration.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import fitz  # PyMuPDF

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = PROJECT_ROOT / "sample_data"

IMAGES_DIR = SAMPLE_DIR / "images"
RECIPES_PDF_DIR = SAMPLE_DIR / "recipes_pdf"
RECIPES_CARDS_DIR = SAMPLE_DIR / "recipes_scans_and_cards"

# Image mapping supporting local source names or previous names
RECIPES = [
    {
        "id": "01_Black_Forest_Cake",
        "legacy_id": "01_Schwarzwaelder_Kirschtorte",
        "title": "Black Forest Cake",
        "category": "Layer Cakes & Celebrations",
        "date": "March 15, 2026",
        "author": "Master Pastry Chef Stefan Weber",
        "prep_time": "60 mins",
        "bake_time": "45 mins",
        "temperature": "175 °C / 350 °F",
        "portions": "12 slices",
        "difficulty": "Intermediate",
        "image_file": "schwarzwaelder_kirschtorte_1787236044862.jpg",
        "ingredients": [
            "6 large eggs (room temperature)",
            "200 g fine caster sugar",
            "1 packet bourbon vanilla sugar (or 1 tsp extract)",
            "150 g all-purpose flour & 50 g cornstarch",
            "50 g unsweetened cocoa powder",
            "2 tsp baking powder & 1 pinch fine salt",
            "1 jar sour cherries (350 g drained weight)",
            "4 tbsp Black Forest Kirschwasser (cherry brandy)",
            "800 ml chilled heavy whipping cream (min. 35% fat)",
            "3 packets whip cream stabilizer",
            "100 g dark chocolate curls / shavings",
        ],
        "steps": [
            "1. Sponge: Separate eggs; whip egg whites to stiff peaks. Beat egg yolks with caster sugar and 3 tbsp lukewarm water until pale and thick. Sift flour, cornstarch, cocoa, and baking powder together, then gently fold into yolk mix along with whipped whites.",
            "2. Pour batter into a greased 26 cm (10-inch) springform pan. Bake at 175 °C (350 °F) for 30-35 mins. Let cool completely on a wire rack, then slice horizontally into 3 even layers.",
            "3. Drain sour cherries, reserving the juice. Thicken juice with cornstarch in a small saucepan over medium heat, then stir in cherries. Drizzle sponge layers with Kirschwasser.",
            "4. Whip heavy cream with stabilizer until firm peaks form. Layer thickened cherries and whipped cream across sponges. Frost outer cake completely and decorate generously with chocolate curls.",
        ],
        "notes": "Chef's Tip: For deeper flavor and clean, effortless slicing, bake the chocolate sponge base one day in advance.",
    },
    {
        "id": "02_Marble_Cake",
        "legacy_id": "02_Marmorkuchen",
        "title": "Classic Marble Cake",
        "category": "Pound Cakes & Traditional Bakes",
        "date": "April 22, 2026",
        "author": "Bauer Artisan Bakery",
        "prep_time": "20 mins",
        "bake_time": "55 mins",
        "temperature": "180 °C / 355 °F",
        "portions": "16 slices",
        "difficulty": "Easy",
        "image_file": "marmorkuchen_classic_1787236057362.jpg",
        "ingredients": [
            "250 g unsalted butter (softened)",
            "200 g fine caster sugar",
            "1 packet bourbon vanilla sugar",
            "4 large eggs (room temperature)",
            "350 g all-purpose wheat flour",
            "1 packet baking powder & 1 pinch salt",
            "100 ml whole milk",
            "30 g rich Dutch cocoa powder & 2 tbsp sugar",
            "3 tbsp whole milk (for chocolate batter)",
            "Confectioners' sugar for dusting",
        ],
        "steps": [
            "1. In a stand mixer, beat softened butter, caster sugar, vanilla sugar, and salt for 4-5 mins until pale and creamy. Add eggs one by one, mixing thoroughly after each addition.",
            "2. Whisk flour and baking powder together. Gradually incorporate into butter mixture, alternating with 100 ml milk until a thick, smooth, heavy-dropping batter is formed.",
            "3. Transfer two-thirds of the light batter into a greased and floured Bundt or loaf pan. Mix cocoa powder, 2 tbsp sugar, and 3 tbsp milk into the remaining one-third of the batter.",
            "4. Layer the chocolate batter over the light batter and gently swirl with a fork in a spiral motion to create the marble pattern. Bake at 180 °C (355 °F) for 50-55 mins. Dust with powdered sugar.",
        ],
        "notes": "An enduring coffee-table favorite. Remains wonderfully tender and moist for up to 4 days when stored airtight.",
    },
    {
        "id": "03_New_York_Cheesecake",
        "legacy_id": "03_New_York_Cheesecake",
        "title": "New York Cheesecake",
        "category": "Cheesecakes & Desserts",
        "date": "May 10, 2026",
        "author": "Pastry Chef Laura Lindner",
        "prep_time": "30 mins",
        "bake_time": "60 mins",
        "temperature": "160 °C / 320 °F",
        "portions": "12 slices",
        "difficulty": "Intermediate",
        "image_file": "creamy_cheesecake_1787236068077.jpg",
        "ingredients": [
            "200 g graham crackers or wholemeal digestives",
            "80 g unsalted butter (melted)",
            "600 g full-fat cream cheese (room temperature)",
            "250 g sour cream or crème fraîche",
            "150 g superfine granulated sugar",
            "3 large eggs & 1 egg yolk",
            "2 tbsp cornstarch",
            "1 organic lemon (finely grated zest and juice)",
            "1 tsp pure Madagascar vanilla extract",
            "Fresh raspberries & mint leaves for garnish",
        ],
        "steps": [
            "1. Pulse graham crackers into fine crumbs, combine with melted butter, and press firmly into the base of a lined 24 cm (9.5-inch) springform pan. Chill in refrigerator for 10 mins.",
            "2. Beat cream cheese, sour cream, granulated sugar, lemon zest, vanilla extract, and cornstarch on the lowest mixer speed until completely smooth and velvety.",
            "3. Gently incorporate eggs and egg yolk one at a time on low speed. Pour the silky filling evenly over the chilled crust.",
            "4. Bake at 160 °C (320 °F) for 60 mins until center is slightly set. Turn off oven and leave cake inside with the door propped slightly open for 1 hour, then chill in fridge for at least 4 hours.",
        ],
        "notes": "Secret to success: Mix on low speed without incorporating excess air to achieve a perfectly flat, crack-free top.",
    },
    {
        "id": "04_Apple_Crumble_Cake",
        "legacy_id": "04_Apfel_Streuselkuchen",
        "title": "Gourmet Apple Crumble Cake",
        "category": "Sheet Cakes & Fruit Bakes",
        "date": "June 18, 2026",
        "author": "Sonnenhof Country Bakery",
        "prep_time": "35 mins",
        "bake_time": "40 mins",
        "temperature": "190 °C / 375 °F",
        "portions": "20 slices",
        "difficulty": "Easy",
        "image_file": "apfel_streuselkuchen_1787236080736.jpg",
        "ingredients": [
            "1 kg tart baking apples (e.g., Boskoop or Granny Smith)",
            "1 tsp ground Ceylon cinnamon & 2 tbsp fresh lemon juice",
            "Crust: 300 g flour, 150 g butter, 100 g sugar, 2 eggs, 1 tsp baking powder",
            "Crumble: 200 g flour, 125 g cold butter, 100 g sugar, 1 tsp vanilla",
            "1 pinch sea salt",
        ],
        "steps": [
            "1. Peel, quarter, core, and slice apples into bite-sized wedges. Toss thoroughly in a large bowl with lemon juice and ground cinnamon.",
            "2. Combine crust ingredients rapidly into a pliable shortcrust dough and roll out evenly across a baking sheet lined with parchment paper.",
            "3. Arrange the spiced apple wedges in a dense, uniform layer across the dough base.",
            "4. Rub cold cubed butter with flour, sugar, and vanilla between fingertips to produce rustic crumbles. Scatter over apples and bake at 190 °C (375 °F) for 35-40 mins until golden brown.",
        ],
        "notes": "Heavenly served lukewarm with a scoop of artisanal bourbon vanilla bean ice cream or fresh whipped cream.",
    },
    {
        "id": "05_Lemon_Bundt_Cake",
        "legacy_id": "05_Zitronen_Gugelhupf",
        "title": "Juicy Lemon Bundt Cake",
        "category": "Bundt Cakes & Pastries",
        "date": "July 2, 2026",
        "author": "Meyer & Sons Patisserie",
        "prep_time": "25 mins",
        "bake_time": "50 mins",
        "temperature": "175 °C / 350 °F",
        "portions": "14 slices",
        "difficulty": "Easy",
        "image_file": "zitronen_gugelhupf_1787236094856.jpg",
        "ingredients": [
            "250 g unsalted butter (softened)",
            "200 g raw cane sugar",
            "4 organic large eggs",
            "300 g spelt flour (Type 630 or all-purpose)",
            "1 packet cream of tartar baking powder & 1 pinch salt",
            "Zest and freshly squeezed juice of 2 organic lemons",
            "80 ml whole milk",
            "Lemon Glaze: 200 g confectioners' sugar & 4 tbsp lemon juice",
            "Candied lemon wheels & fresh rosemary sprigs for garnish",
        ],
        "steps": [
            "1. Beat butter, raw cane sugar, and lemon zest for 5 mins until light and fluffy. Beat in eggs one by one until smooth.",
            "2. Sift flour with baking powder and salt; gently fold into the batter, alternating with milk and 3 tbsp fresh lemon juice.",
            "3. Transfer batter into a generously buttered Bundt pan. Bake at 175 °C (350 °F) for 45-50 mins (test with a wooden skewer).",
            "4. Invert cake onto a cooling rack. Poke small holes with a toothpick and brush warm cake with remaining lemon juice. Once cool, drizzle with tangy lemon glaze.",
        ],
        "notes": "Extra fragrant and moist thanks to rubbing fresh organic lemon zest directly into the butter before whipping.",
    },
    {
        "id": "06_Viennese_Sachertorte",
        "legacy_id": "06_Wiener_Sachertorte",
        "title": "Original Viennese Sachertorte",
        "category": "Chocolate Cakes & Specialties",
        "date": "August 14, 2026",
        "author": "Imperial Café & Confiserie",
        "prep_time": "50 mins",
        "bake_time": "50 mins",
        "temperature": "170 °C / 340 °F",
        "portions": "12 slices",
        "difficulty": "Challenging",
        "image_file": "wiener_sachertorte_1787236109708.jpg",
        "ingredients": [
            "140 g unsalted butter (softened) & 110 g confectioners' sugar",
            "6 large eggs (separated into yolks and whites)",
            "130 g dark couverture chocolate (min. 60% cocoa)",
            "110 g granulated sugar",
            "140 g cake flour (sifted)",
            "200 g premium apricot jam (strained & warmed)",
            "Chocolate Glaze: 200 g dark couverture, 150 g sugar, 125 ml water",
            "Unsweetened whipped cream (Schlagobers) for serving",
        ],
        "steps": [
            "1. Melt dark chocolate over a gentle water bath. Beat softened butter with confectioners' sugar until creamy; add egg yolks one by one, then blend in melted chocolate.",
            "2. Whip egg whites with granulated sugar until stiff and glossy. Carefully fold whipped egg whites and sifted cake flour alternately into the chocolate batter.",
            "3. Bake in a 24 cm (9.5-inch) springform pan at 170 °C (340 °F) for 45-50 mins. Allow to cool completely on a wire rack.",
            "4. Slice cake horizontally into two layers. Spread warm apricot jam between layers and over the entire exterior. Coat evenly with warm cooked chocolate glaze.",
        ],
        "notes": "Authentically served alongside a generous dollop of unsweetened whipped cream (Schlagobers) and a cup of Viennese Melange coffee.",
    },
]


def create_recipe_pdf(recipe: dict, output_path: Path, embed_image_path: Path | None = None) -> None:
    """Creates a beautifully styled A4 PDF recipe document in English."""
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
    page.insert_text(fitz.Point(50, 58), "ORDINFLOW BAKERY & PASTRY WORKSHOP", fontsize=11, color=(1, 1, 1), fontname="helv")
    page.insert_text(fitz.Point(50, 82), recipe["title"].upper(), fontsize=18, color=(1, 0.95, 0.85), fontname="helv")

    # 2. Metadata Key-Value Box
    page.draw_rect(fitz.Rect(35, 105, 340, 245), color=c_border, fill=c_light_bg, width=1)

    meta_lines = [
        ("Category:", recipe["category"]),
        ("Issue Date:", recipe["date"]),
        ("Pastry Chef / Author:", recipe["author"]),
        ("Preparation Time:", recipe["prep_time"]),
        ("Baking Time:", recipe["bake_time"]),
        ("Oven Temperature:", recipe["temperature"]),
        ("Portions / Yield:", recipe["portions"]),
        ("Difficulty Level:", recipe["difficulty"]),
    ]

    y_pos = 125
    for label, val in meta_lines:
        page.insert_text(fitz.Point(45, y_pos), label, fontsize=9.5, color=c_primary, fontname="helv")
        page.insert_text(fitz.Point(165, y_pos), val, fontsize=9.5, color=c_dark, fontname="helv")
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
    page.insert_text(fitz.Point(col1_left + 15, 277), "INGREDIENTS LIST", fontsize=11, color=(1, 1, 1), fontname="helv")

    y_ing = 305
    for ing in recipe["ingredients"]:
        page.draw_circle(fitz.Point(col1_left + 15, y_ing - 3), 2, color=c_accent, fill=c_accent)
        ing_rect = fitz.Rect(col1_left + 24, y_ing - 9, col1_left + col1_width - 10, y_ing + 20)
        page.insert_textbox(ing_rect, ing, fontsize=9, color=c_dark, fontname="helv")
        y_ing += 26 if len(ing) > 30 else 18

    # 5. Instructions Column (Right)
    col2_left = 255
    col2_width = 305
    page.draw_rect(fitz.Rect(col2_left, 260, col2_left + col2_width, 740), color=c_border, fill=(1, 1, 1), width=1)
    page.draw_rect(fitz.Rect(col2_left, 260, col2_left + col2_width, 285), color=c_primary, fill=c_primary)
    page.insert_text(fitz.Point(col2_left + 15, 277), "STEP-BY-STEP INSTRUCTIONS", fontsize=11, color=(1, 1, 1), fontname="helv")

    y_step = 305
    for step in recipe["steps"]:
        step_rect = fitz.Rect(col2_left + 15, y_step - 8, col2_left + col2_width - 15, y_step + 85)
        page.insert_textbox(step_rect, step, fontsize=9.5, color=c_dark, fontname="helv")
        y_step += max(60.0, len(step) * 0.40 + 26.0)

    # 6. Recipe Note Box
    note_rect = fitz.Rect(col2_left + 15, 675, col2_left + col2_width - 15, 725)
    page.draw_rect(note_rect, color=c_accent, fill=c_light_bg, width=0.8)
    page.insert_textbox(note_rect + (8, 6, -8, -6), recipe["notes"], fontsize=8.5, color=c_primary, fontname="helv")

    # 7. Signature & Stamp Area at the bottom
    page.draw_line(fitz.Point(35, 755), fitz.Point(560, 755), color=c_border, width=1)
    page.insert_text(fitz.Point(35, 775), "Quality & Safety Approval:", fontsize=9, color=c_gray, fontname="helv")
    page.insert_text(fitz.Point(35, 790), f"Audited on: {recipe['date']} at Master Bakery", fontsize=8.5, color=c_gray, fontname="helv")

    page.draw_rect(fitz.Rect(360, 762, 555, 805), color=(0.7, 0.7, 0.7), width=0.7)
    page.insert_text(fitz.Point(370, 775), "Signature Pastry Chef / Stamp", fontsize=7.5, color=(0.6, 0.6, 0.6), fontname="helv")
    page.insert_text(fitz.Point(385, 795), f"sgnd. {recipe['author']}", fontsize=9, color=c_primary, fontname="helv")

    # Footer note
    page.insert_text(fitz.Point(35, 825), "OrdinFlow Sample Document · Generated 100% On-Premise & Privacy-Compliant", fontsize=7.5, color=(0.6, 0.6, 0.6), fontname="helv")
    page.insert_text(fitz.Point(480, 825), "Document: Cake Recipe", fontsize=7.5, color=(0.6, 0.6, 0.6), fontname="helv")

    doc.save(str(output_path))
    doc.close()


def generate_sample_dataset() -> None:
    """Generates all sample assets: images, PDFs, scans, multi-page compilation, and skill config."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    RECIPES_PDF_DIR.mkdir(parents=True, exist_ok=True)
    RECIPES_CARDS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Manage images: ensure English filenames
    for r in RECIPES:
        dest_img = IMAGES_DIR / f"{r['id']}.jpg"
        legacy_img = IMAGES_DIR / f"{r['legacy_id']}.jpg"

        if not dest_img.exists():
            if legacy_img.exists():
                shutil.copy2(legacy_img, dest_img)
                print(f"Renamed/copied image {legacy_img.name} -> {dest_img.name}")
            else:
                print(f"Warning: neither {dest_img} nor {legacy_img} found")
        else:
            print(f"Verified cake image -> {dest_img.name}")

    # Remove old legacy German image files if English ones exist
    for r in RECIPES:
        legacy_img = IMAGES_DIR / f"{r['legacy_id']}.jpg"
        dest_img = IMAGES_DIR / f"{r['id']}.jpg"
        if legacy_img.exists() and legacy_img != dest_img:
            legacy_img.unlink()
            print(f"Removed legacy German image -> {legacy_img.name}")

    # 2. Clean up old German PDFs and Card files
    for old_file in RECIPES_PDF_DIR.glob("Rezept__*.pdf"):
        old_file.unlink()
        print(f"Removed legacy German PDF -> {old_file.name}")
    for old_file in RECIPES_PDF_DIR.glob("Sammelband_*.pdf"):
        old_file.unlink()
        print(f"Removed legacy German multi-page PDF -> {old_file.name}")
    for old_file in RECIPES_CARDS_DIR.glob("Rezeptkarte__*.jpg"):
        old_file.unlink()
        print(f"Removed legacy German card -> {old_file.name}")
    old_yaml = SAMPLE_DIR / "kuchen_skill_example.yaml"
    if old_yaml.exists():
        old_yaml.unlink()
        print(f"Removed legacy German YAML -> {old_yaml.name}")

    # 3. Generate Single-Page PDFs & Image Scans
    for r in RECIPES:
        pdf_path = RECIPES_PDF_DIR / f"Recipe__{r['id']}.pdf"
        img_src = IMAGES_DIR / f"{r['id']}.jpg"
        create_recipe_pdf(r, pdf_path, embed_image_path=img_src)
        print(f"Generated Recipe PDF -> {pdf_path.name}")

        # Render PDF to high-res JPG recipe card
        doc = fitz.open(str(pdf_path))
        page = doc[0]
        pix = page.get_pixmap(dpi=200)
        card_img_path = RECIPES_CARDS_DIR / f"Recipe_Card__{r['id']}.jpg"
        pix.save(str(card_img_path))
        doc.close()
        print(f"Rendered Recipe Card Image -> {card_img_path.name}")

    # 4. Generate Multi-Page PDF Compilation
    multipage_pdf_path = RECIPES_PDF_DIR / "Compilation_Cake_Recipes_Multipage.pdf"
    multi_doc = fitz.open()
    for r in RECIPES:
        single_pdf = RECIPES_PDF_DIR / f"Recipe__{r['id']}.pdf"
        src_doc = fitz.open(str(single_pdf))
        multi_doc.insert_pdf(src_doc)
        src_doc.close()
    multi_doc.save(str(multipage_pdf_path))
    multi_doc.close()
    print(f"Generated Multi-Page PDF -> {multipage_pdf_path.name} (6 pages)")

    # 5. Generate English Cake Recipe Skill Configuration YAML
    skill_yaml_content = """id: import_cake_recipes
name: Cake Recipes & Bakery Import
type: import
description: Sample configuration for automatic classification, multimodal extraction, and archiving of cake recipes and cake photos.
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
  CakeRecipe:
    classification_desc: A baking recipe for cakes, tarts, pastries, or sweet dishes with an ingredients list, baking time, temperature, and preparation steps.
    emoji: 🍰
    extraction_fields:
      RecipeName: The name of the recipe or cake (e.g., Black Forest Cake, Marble Cake, New York Cheesecake).
      Category: The pastry category (e.g., Pound Cakes, Layer Cakes, Sheet Cakes, Cheesecakes, Chocolate Specialties).
      BakeTime: The baking time (e.g., 45 mins, 55 mins).
      BakeTemperature: The recommended oven temperature (e.g., 175 °C, 180 °C).
      Portions: Number of slices or servings (e.g., 12 slices, 16 slices).
      Chef: The name of the author, baker, or master pastry chef.
      Date: Issue or recipe date (e.g., March 15, 2026).
      Difficulty: The difficulty level (Easy, Intermediate, Challenging).
    routing:
      archive: true
      folder_template: Recipes__{Category}
      filename_template: Recipe__{RecipeName}__{BakeTime}
    validation:
      optional_fields:
      - Difficulty
      - Portions
      - Chef
      signature_required: false

  CakePhoto:
    classification_desc: A photograph or image of a cake, tart, or pastry without structured recipe text.
    emoji: 📷
    dependent: true
    extraction_fields:
      Description: Short description of the depicted cake or pastry (e.g., Black Forest Cake slice, Marble Cake dusted with sugar).
    routing:
      archive: true
      folder_template: Photos__{Description}
      filename_template: Photo__{Description}
    validation:
      signature_required: false
"""
    skill_file_path = SAMPLE_DIR / "cake_recipe_skill_example.yaml"
    skill_file_path.write_text(skill_yaml_content, encoding="utf-8")
    print(f"Generated Skill YAML Template -> {skill_file_path.name}")

    # 6. Generate sample_data/README.md in English
    readme_content = """# 🍰 OrdinFlow Sample Data: Cake Recipes & Photos

This directory contains ready-to-use sample data designed for testing and demonstrating the core features of **OrdinFlow** (document classification, OCR & VLM multimodal extraction, image recognition, multi-page splitting, and dynamic routing).

---

## 📂 Sample Data Structure

```
sample_data/
├── images/                                 # 6 high-resolution AI-generated cake photos (.jpg)
│   ├── 01_Black_Forest_Cake.jpg
│   ├── 02_Marble_Cake.jpg
│   ├── 03_New_York_Cheesecake.jpg
│   ├── 04_Apple_Crumble_Cake.jpg
│   ├── 05_Lemon_Bundt_Cake.jpg
│   └── 06_Viennese_Sachertorte.jpg
│
├── recipes_pdf/                            # Formatted DIN-A4 PDF recipe documents
│   ├── Recipe__01_Black_Forest_Cake.pdf
│   ├── Recipe__02_Marble_Cake.pdf
│   ├── Recipe__03_New_York_Cheesecake.pdf
│   ├── Recipe__04_Apple_Crumble_Cake.pdf
│   ├── Recipe__05_Lemon_Bundt_Cake.pdf
│   ├── Recipe__06_Viennese_Sachertorte.pdf
│   └── Compilation_Cake_Recipes_Multipage.pdf  # 6-page PDF for testing multi-page document splitting
│
├── recipes_scans_and_cards/                # Rendered recipe cards (.jpg) for Vision & image OCR testing
│   ├── Recipe_Card__01_Black_Forest_Cake.jpg
│   ├── Recipe_Card__02_Marble_Cake.jpg
│   ├── ...
│
└── cake_recipe_skill_example.yaml          # Pre-configured skill configuration for Cake Recipes & Photos
```

---

## 🚀 Quick Start: Testing OrdinFlow with Sample Data

### 1. Activate Cake Skill (Optional for customized routing)
Copy `sample_data/cake_recipe_skill_example.yaml` into your skills directory:
```bash
copy sample_data\\cake_recipe_skill_example.yaml settings\\skills\\import_cake_recipes.yaml
```
Or import the configuration directly via the OrdinFlow Web Dashboard in the **Skills** tab.

### 2. Place Test Files into Inbox Directory
Copy one or more sample files into your watched directory (`watch_dir`, e.g., `C:\\OrdinFlowTest\\Inbox` or the directory defined in `settings/config.yaml`):
```bash
copy sample_data\\recipes_pdf\\Recipe__01_Black_Forest_Cake.pdf C:\\OrdinFlowTest\\Inbox\\
copy sample_data\\images\\01_Black_Forest_Cake.jpg C:\\OrdinFlowTest\\Inbox\\
```

### 3. What OrdinFlow Does Automatically
1. **Detection & Classification:** OrdinFlow detects whether the incoming document is a `CakeRecipe` (structured document) or a `CakePhoto` (image).
2. **Data Extraction:**
   - `RecipeName` (e.g., "Black Forest Cake")
   - `Category` (e.g., "Layer Cakes & Celebrations")
   - `BakeTime` (e.g., "45 mins")
   - `BakeTemperature` (e.g., "175 °C / 350 °F")
   - `Portions` (e.g., "12 slices")
   - `Chef` (e.g., "Master Pastry Chef Stefan Weber")
   - `Date` (e.g., "March 15, 2026")
3. **Automated Routing:** The file is dynamically moved to `Target/Recipes__{Category}/Recipe__{RecipeName}__{BakeTime}.pdf` and paired with a `.meta` JSON sidecar file.
4. **Multi-Page Splitting:** The multi-page document `Compilation_Cake_Recipes_Multipage.pdf` demonstrates automatic splitting (`split_multi_documents: true`) into individual recipes.
"""
    readme_path = SAMPLE_DIR / "README.md"
    readme_path.write_text(readme_content, encoding="utf-8")
    print(f"Generated sample_data README -> {readme_path.name}")


if __name__ == "__main__":
    generate_sample_dataset()
