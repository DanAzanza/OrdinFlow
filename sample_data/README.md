# 🍰 OrdinFlow Sample Data: Cake Recipes & Photos

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
copy sample_data\cake_recipe_skill_example.yaml settings\skills\import_cake_recipes.yaml
```
Or import the configuration directly via the OrdinFlow Web Dashboard in the **Skills** tab.

### 2. Place Test Files into Inbox Directory
Copy one or more sample files into your watched directory (`watch_dir`, e.g., `C:\OrdinFlowTest\Inbox` or the directory defined in `settings/config.yaml`):
```bash
copy sample_data\recipes_pdf\Recipe__01_Black_Forest_Cake.pdf C:\OrdinFlowTest\Inbox\
copy sample_data\images\01_Black_Forest_Cake.jpg C:\OrdinFlowTest\Inbox\
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
