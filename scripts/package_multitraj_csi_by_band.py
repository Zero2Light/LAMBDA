#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import zipfile
from collections import defaultdict
from datetime import datetime
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT_DIR / "data_export" / "example_multitraj_csi"
DEFAULT_OUT_DIR = ROOT_DIR / "data_export" / "_packages"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Package multi-trajectory CSI outputs into per-band zip files and one outer zip."
    )
    parser.add_argument("--source-root", default=str(DEFAULT_SOURCE), help="Root containing mobility/traj CSI folders.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Directory for generated packages.")
    parser.add_argument("--bundle-name", default="lambda_csi_by_band", help="Output bundle name.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing bundle directory/archive.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be packaged without writing archives.")
    parser.add_argument("--compression-level", type=int, default=6, help="Zip compression level for per-band archives.")
    return parser.parse_args()


def frequency_band_from_path(path: Path) -> str | None:
    parent = path.parent.name
    if parent.startswith("f") and "GHz" in parent:
        return parent
    return None


def band_arcname(source_root: Path, csi_path: Path, band: str) -> str:
    rel = csi_path.relative_to(source_root)
    parts = list(rel.parts)
    try:
        band_index = parts.index(band)
    except ValueError as exc:
        raise ValueError(f"{csi_path} is not under a {band} directory") from exc

    # Drop only the frequency directory. The remaining mobility/traj/link path
    # prevents csi_000000.npz collisions across trajectories.
    arc_parts = parts[:band_index] + parts[band_index + 1 :]
    return str(Path(*arc_parts))


def collect_by_band(source_root: Path) -> dict[str, list[Path]]:
    grouped: dict[str, list[Path]] = defaultdict(list)
    for csi_path in source_root.rglob("csi_*.npz"):
        band = frequency_band_from_path(csi_path)
        if band:
            grouped[band].append(csi_path)

    return {band: sorted(paths) for band, paths in sorted(grouped.items(), key=lambda item: band_sort_key(item[0]))}


def band_sort_key(band: str) -> float:
    value = band.removeprefix("f").split("GHz", 1)[0].replace("p", ".")
    try:
        return float(value)
    except ValueError:
        return float("inf")


def prepare_output(bundle_dir: Path, outer_archive: Path, overwrite: bool, dry_run: bool) -> None:
    existing = [path for path in (bundle_dir, outer_archive) if path.exists()]
    if not existing:
        return

    if dry_run:
        print("[DryRun] Existing outputs:")
        for path in existing:
            print(f"  {path}")
        return

    if not overwrite:
        raise SystemExit("[Error] Output already exists. Pass --overwrite or choose another --bundle-name.")

    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    if outer_archive.exists():
        outer_archive.unlink()


def write_band_zip(source_root: Path, band: str, files: list[Path], archive: Path, compression_level: int) -> int:
    seen: set[str] = set()
    tmp_archive = archive.with_suffix(archive.suffix + ".tmp")
    if tmp_archive.exists():
        tmp_archive.unlink()

    with zipfile.ZipFile(
        tmp_archive,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=compression_level,
        allowZip64=True,
    ) as zf:
        for csi_path in files:
            arcname = band_arcname(source_root, csi_path, band)
            if arcname in seen:
                raise SystemExit(f"[Error] Duplicate archive path in {band}: {arcname}")
            seen.add(arcname)
            zf.write(csi_path, arcname)

    tmp_archive.replace(archive)
    return len(seen)


def write_outer_zip(bundle_dir: Path, outer_archive: Path, band_archives: list[Path]) -> None:
    tmp_archive = outer_archive.with_suffix(outer_archive.suffix + ".tmp")
    if tmp_archive.exists():
        tmp_archive.unlink()

    with zipfile.ZipFile(tmp_archive, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        for archive in band_archives:
            zf.write(archive, archive.name)

    tmp_archive.replace(outer_archive)


def human_size(path: Path) -> str:
    size = float(path.stat().st_size)
    for unit in ("B", "K", "M", "G", "T"):
        if size < 1024 or unit == "T":
            return f"{size:.0f}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024
    return f"{path.stat().st_size}B"


def main() -> None:
    args = parse_args()
    source_root = Path(args.source_root).expanduser()
    out_dir = Path(args.out_dir).expanduser()
    if not source_root.is_absolute():
        source_root = ROOT_DIR / source_root
    if not out_dir.is_absolute():
        out_dir = ROOT_DIR / out_dir

    source_root = source_root.resolve()
    out_dir = out_dir.resolve()
    if not source_root.is_dir():
        raise SystemExit(f"[Error] SOURCE_ROOT does not exist: {source_root}")

    bundle_dir = out_dir / args.bundle_name
    outer_archive = out_dir / f"{args.bundle_name}.zip"
    grouped = collect_by_band(source_root)
    if not grouped:
        raise SystemExit(f"[Error] No csi_*.npz files found under frequency directories in {source_root}")

    print(f"[Package] source={source_root}")
    print(f"[Package] output={bundle_dir}")
    print(f"[Package] outer={outer_archive}")
    print(f"[Package] bands={' '.join(grouped)}")

    prepare_output(bundle_dir, outer_archive, args.overwrite, args.dry_run)

    total = sum(len(files) for files in grouped.values())
    if args.dry_run:
        for band, files in grouped.items():
            print(f"[DryRun] {band}: csi_npz={len(files)} -> {band}.zip")
        print(f"[DryRun] total_csi_npz={total}")
        return

    bundle_dir.mkdir(parents=True, exist_ok=True)
    manifest = bundle_dir / "manifest.txt"
    band_archives: list[Path] = []
    with manifest.open("w", encoding="utf-8") as handle:
        handle.write(f"bundle_name={args.bundle_name}\n")
        handle.write(f"created_at={datetime.now().isoformat(timespec='seconds')}\n")
        handle.write(f"source_root={source_root}\n")
        handle.write(f"total_csi_npz={total}\n\n")

        for band, files in grouped.items():
            archive = bundle_dir / f"{band}.zip"
            print(f"[Package] creating {archive} files={len(files)}")
            count = write_band_zip(source_root, band, files, archive, args.compression_level)
            band_archives.append(archive)
            handle.write(f"band={band}\n")
            handle.write(f"archive={archive.name}\n")
            handle.write(f"csi_npz_count={count}\n")
            handle.write(f"archive_size={human_size(archive)}\n\n")

    print(f"[Package] creating outer archive {outer_archive}")
    write_outer_zip(bundle_dir, outer_archive, band_archives)

    print("[Package] done")
    print(f"[Package] manifest={manifest}")
    print(f"[Package] outer={human_size(outer_archive)} {outer_archive}")


if __name__ == "__main__":
    main()
