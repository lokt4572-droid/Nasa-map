# Mars scientific data directory

This folder holds **original** scientific rasters (DEMs) and derived products. It is
ignored by git (only this README and empty `.gitkeep` files are versioned). Never put
DEMs into `frontend/public`.

```
data/mars/
├── raw/          original downloads, unmodified
│   ├── mola/     MGS MOLA MEGDR (PDS4 or PDS3)
│   ├── hirise/   MRO HiRISE DTMs
│   ├── hrsc/     Mars Express HRSC DTMs (future)
│   └── ctx/      CTX DTMs (future)
├── processed/    derived products (future: dem subsets, slope, hillshade, roughness)
└── metadata/     notes, checksums, download receipts you want to keep
```

The backend reads this location from `MARS_DATA_DIR` in `backend/.env`
(default `../data/mars`, relative to `backend/`).

## 1. Where to download

| Product | Official source |
|---|---|
| MGS MOLA MEGDR, PDS4 (maintained version) | PDS Geosciences Node — *MGS MOLA Topography Derived bundle*: https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/ (overview: https://pds-geosciences.wustl.edu/missions/mgs/mola.html) |
| MGS MOLA MEGDR, PDS3 (legacy) | https://pds-geosciences.wustl.edu/missions/mgs/megdr.html |
| HiRISE DTMs | https://www.uahirise.org/dtm/ (about: https://hirise.lpl.arizona.edu/dtm/about.php) |

Notes
* MEGDRs come in several grid resolutions (pixels per degree) and as global or tiled
  products. Start with a global, low-resolution MEGDR: it is small and covers every
  point. Pick the *topography* product (elevation), not radius or counts.
* Not every HiRISE stereo pair has a DTM. A HiRISE orthoimage/mosaic is **not** a DTM.
* Download the label together with the data file (PDS4: the `.xml` label next to the
  `.img`; PDS3: the `.lbl` file). The label carries the CRS, units, scaling and nodata.

## 2. How to identify the product type

Open the label (`.xml` for PDS4, `.lbl` for PDS3) in a text editor and check:
* product / file name and title (MEGDR topography vs radius vs counts);
* `Cartography` (PDS4) or `IMAGE_MAP_PROJECTION` (PDS3): projection, latitude type
  (planetocentric/planetographic), longitude direction and domain, map scale;
* element type and scaling (`scaling_factor`, `value_offset`), unit (`m`), nodata.

Then run `python scripts\inspect_dem.py <file>` (see below): it prints what GDAL reads.

## 3. Where to put the file

Copy the data file **and** its label, unchanged, into the matching `raw/` subfolder,
e.g. `data\mars\raw\mola\`. Keep original names. Do not convert or edit them.

## 4. Metadata to keep

Save into `metadata/` (or the dataset's admin record): download URL, download date,
product ID, label file, checksum, and any release notes/errata from the archive page.
The importer stores the sha256 checksum and the full GDAL metadata automatically.

## 5. Check with GDAL

```powershell
cd backend
.venv\Scripts\Activate.ps1
python ..\scripts\check_data.py
python ..\scripts\inspect_dem.py "..\data\mars\raw\mola\<label-or-file>"
```

With PDS4, open the product through its `.xml` label. With PDS3, use the `.lbl` label.

## 6. Import into the application

```powershell
cd backend
.venv\Scripts\Activate.ps1
python manage.py import_dem --file "..\data\mars\raw\mola\<label-or-file>" --name "mola-megdr" `
    --source "NASA PDS Geosciences Node" --instrument "MGS MOLA" --product-id "<id from label>" `
    --vertical-datum "<datum stated in the label>"
```

Add `--dry-run` to validate only. If the file does not state its elevation units, the
import stops and asks for `--units m` (only pass it if the label says metres). If the
file has no CRS, the import stops: fix the georeferencing (use the proper label) instead
of guessing. Large files: add `--no-checksum` to skip the sha256 pass.

HiRISE DTM example:

```powershell
python manage.py import_dem --file "..\data\mars\raw\hirise\<DTM file>" --name "hirise-dtm-<site>" `
    --source "HiRISE / University of Arizona" --instrument "MRO HiRISE" --product-id "<DTM product id>" `
    --vertical-datum "<datum stated in the DTM label>"
```

Then `python manage.py check_datasets` verifies that registered files still exist.
