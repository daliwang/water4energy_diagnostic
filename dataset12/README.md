# Dataset 1 / Dataset 2 diagnostics

Sibling of the E3SM–ERA5 climatology comparison. This folder asks a **different**
question: is the observation ladder internally consistent?

| Recipe | Question |
|---|---|
| Dataset 1 | What is on disk? Does the ERA5 NA/Pac/Atl domain look right? How does the band-M **bbox** differ from the TVA **service-area** polygon used in the Frontier diagnostic? |
| Dataset 2 | Are `samples_M_v0.nc` a faithful windowing of the monthly panels, with no look-ahead and train-only scalers? |

These functions do **not** compare E3SM to ERA5. Keep that in `plot_e3sm_era5.py`.

## Run

From this folder, with Dataset 2 NetCDFs in `_inputs/` (or `trainingData/processed/monthly/`):

```bash
cd water4energy_diagnostic
python3 dataset12/run.py
```

Optional flags:

```text
--data-root   Dataset 1 tree (default: ../data)
--pack-dir    Dataset 2 monthly pack
--output-dir  default: dataset12/outputs
```

On a laptop you typically have only a few ERA5 months plus the ~600 KB Dataset 2 pack. The inventory will say so. Reconstruction and the QC-CSV vs panel check still run in full.

## Outputs

```text
dataset12/outputs/
  report.json
  ds1_era5_tp_domain.png
  ds1_tva_mask_cells.png
  ds2_reconstruct_y.png
  ds2_split_timeline.png
  ds2_nov_oni_vs_djf_tp.png
```
