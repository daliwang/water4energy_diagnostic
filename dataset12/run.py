#!/usr/bin/env python3
"""Run Dataset 1 + Dataset 2 diagnostic functions and write a report + figures."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
sys.path.insert(0, str(PACKAGE.parent))

from dataset12 import dataset1, dataset2, metrics, paths  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", default=None, help="Dataset 1 tree (data/)")
    p.add_argument("--pack-dir", default=None, help="Dataset 2 processed/monthly pack")
    p.add_argument("--output-dir", default=str(paths.DEFAULT_OUTPUT))
    p.add_argument("--qc-csv", default=None, help="Dataset 1 TVA monthly QC CSV")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    data_root = paths.data_root(args.data_root)
    pack_dir = paths.pack_dir(args.pack_dir)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    qc_csv = Path(args.qc_csv) if args.qc_csv else (
        data_root / "00_docs" / "era5_daily1deg_qc" / "tva_monthly_means_1980_2024.csv"
    )
    shapefile = data_root / "00_masks" / "tva_boundary.shp"

    report: dict = {
        "data_root": str(data_root),
        "pack_dir": str(pack_dir),
        "dataset1": {},
        "dataset2": {},
    }

    inv = dataset1.inventory_dataset1(data_root)
    report["dataset1"]["inventory"] = inv

    tp_files = dataset1.find_local_tp_files(data_root)
    report["dataset1"]["local_tp_months"] = list(tp_files)
    if tp_files:
        latest = tp_files[sorted(tp_files)[-1]]
        report["dataset1"]["tva_masks"] = dataset1.compare_tva_masks(
            latest, shapefile if shapefile.is_file() else None
        )
        dataset1.plot_era5_domain(
            tp_files,
            shapefile if shapefile.is_file() else None,
            out / "ds1_era5_tp_domain.png",
        )
        dataset1.plot_mask_zoom(
            latest,
            shapefile if shapefile.is_file() else None,
            out / "ds1_tva_mask_cells.png",
        )

    pack = dataset2.load_pack(pack_dir)
    report["dataset2"]["files_found"] = {k: (str(v) if v else None) for k, v in pack.items()}
    if pack["samples"] is not None:
        report["dataset2"]["integrity"] = dataset2.integrity(pack["samples"])
        recon = dataset2.reconstruct(pack)
        report["dataset2"]["reconstruction"] = recon
        report["dataset2"]["scalers"] = dataset2.scaler_audit(pack)
        report["dataset2"]["issue_csv"] = dataset2.issue_csv_matches_samples(pack)
        if not recon.get("skipped"):
            dataset2.plot_reconstruction(pack, recon, out / "ds2_reconstruct_y.png")
            dataset2.plot_split_timeline(pack, out / "ds2_split_timeline.png")
            report["dataset2"]["nov_enso"] = dataset2.plot_nov_enso(
                pack, out / "ds2_nov_oni_vs_djf_tp.png"
            )
        if pack["era5_abs"] is not None:
            report["dataset1"]["qc_csv_vs_panel"] = dataset1.compare_qc_csv_to_panel(
                qc_csv, pack["era5_abs"]
            )

    metrics.write_json(out / "report.json", report)
    print(f"Wrote {out / 'report.json'}")
    d1 = report["dataset1"]
    print(
        "Dataset 1 ERA5 files: "
        f"{inv['era5_present_files']}/{inv['era5_expected_files']} "
        f"({inv['era5_fraction']:.1%})"
    )
    if "tva_masks" in d1:
        m = d1["tva_masks"]
        print(
            "TVA cells: bbox="
            f"{m['bbox']['cells']}  service-area={m['service_area_geojson']['cells']}  "
            f"overlap={m['service_area_geojson']['overlap_with_bbox']}"
        )
    if "qc_csv_vs_panel" in d1 and not d1["qc_csv_vs_panel"].get("skipped"):
        q = d1["qc_csv_vs_panel"]
        print(
            "QC CSV vs Dataset 2 panel: "
            f"t2m r={q['t2m_C']['r']:.6f}  tp r={q['tp_mm_day']['r']:.6f}  "
            f"msl r={q['msl_hPa']['r']:.6f}  n={q['n']}"
        )
    d2 = report["dataset2"]
    if "integrity" in d2:
        i = d2["integrity"]
        print(
            f"Dataset 2 samples: n={i['n_samples']}  "
            f"splits={i['split_counts']}  nans={i['nan_counts']}"
        )
    if "reconstruction" in d2 and not d2["reconstruction"].get("skipped"):
        r = d2["reconstruction"]
        print(f"Reconstruction {r['verdict']}: y max|Δ|={r['y_atm']['max_abs']:.2e}")
    if "nov_enso" in d2:
        n = d2["nov_enso"]
        print(f"Nov-issue SON ONI vs DJF tp: r={n['r_son_oni_djf_tp']:.3f} n={n['n_nov_issues']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
