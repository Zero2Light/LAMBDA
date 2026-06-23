#!/usr/bin/env python3
"""Package CSI frequency directories into per-band zips and one outer zip.

The archive layout is:

    csi_foggy.zip
      f1p4GHz_V.zip
      f3p5GHz_V.zip
      ...

Each per-band zip stores the CSI files at its own root:

    f1p4GHz_V.zip
      csi_000000.npz
      csi_000001.npz
      ...

Source directories may include weather-specific suffixes such as
``f60p0GHz_V_fog_M0p1gpm3_gas_p676``. Those suffixes are stripped in the zip
file names by default, while the source directories are left untouched.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_OUT_DIR = ROOT_DIR / "data_export" / "_packages"
FREQ_TAG_RE = re.compile(r"^(f\d+p\d+GHz_[^_]+)(?:_(?:rain|fog|snow)_.+)?$")


def frequency_sort_key(name: str) -> tuple[float, str]:
    match = re.match(r"^f(\d+)p(\d+)GHz_", name)
    if not match:
        return float("inf"), name
    return float(f"{match.group(1)}.{match.group(2)}"), name


def archive_band_name(source_name: str, strip_weather_suffix: bool) -> str:
    if not strip_weather_suffix:
        return source_name
    match = FREQ_TAG_RE.match(source_name)
    if not match:
        raise SystemExit(f"[Error] Cannot parse frequency directory name: {source_name}")
    return match.group(1)


def collect_frequency_dirs(source_root: Path, strip_weather_suffix: bool) -> list[tuple[str, Path, list[Path]]]:
    if not source_root.is_dir():
        raise SystemExit(f"[Error] Source root does not exist or is not a directory: {source_root}")

    items: list[tuple[str, Path, list[Path]]] = []
    seen_bands: set[str] = set()
    for freq_dir in sorted((p for p in source_root.iterdir() if p.is_dir()), key=lambda p: frequency_sort_key(p.name)):
        band = archive_band_name(freq_dir.name, strip_weather_suffix)
        if band in seen_bands:
            raise SystemExit(f"[Error] Duplicate archive band after suffix stripping: {band}")
        files = sorted(freq_dir.glob("csi_*.npz"), key=lambda p: p.name)
        if not files:
            continue
        seen_bands.add(band)
        items.append((band, freq_dir, files))

    if not items:
        raise SystemExit(f"[Error] No csi_*.npz files found under: {source_root}")
    return items


def prepare_output(bundle_dir: Path, archive: Path, overwrite: bool) -> None:
    bundle_dir.parent.mkdir(parents=True, exist_ok=True)
    existing = [path for path in (bundle_dir, archive) if path.exists()]
    if existing:
        if not overwrite:
            paths = "\n".join(f"  {path}" for path in existing)
            raise SystemExit(f"[Error] Output already exists. Use --overwrite to replace:\n{paths}")
        if bundle_dir.exists():
            shutil.rmtree(bundle_dir)
        if archive.exists():
            archive.unlink()
    bundle_dir.mkdir(parents=True, exist_ok=True)


def write_zip_from_files(
    archive: Path,
    files: list[Path],
    compression: int,
    compression_level: int | None,
    arcname_prefix: str = "",
) -> int:
    tmp_archive = archive.with_suffix(archive.suffix + ".tmp")
    if tmp_archive.exists():
        tmp_archive.unlink()

    zip_kwargs = {
        "mode": "w",
        "compression": compression,
        "allowZip64": True,
    }
    if compression == zipfile.ZIP_DEFLATED:
        zip_kwargs["compresslevel"] = compression_level

    count = 0
    with zipfile.ZipFile(tmp_archive, **zip_kwargs) as zf:
        for file_path in files:
            arcname = f"{arcname_prefix}{file_path.name}"
            zf.write(file_path, arcname)
            count += 1

    tmp_archive.replace(archive)
    return count


def write_outer_zip(bundle_dir: Path, outer_archive: Path, band_archives: list[Path]) -> None:
    tmp_archive = outer_archive.with_suffix(outer_archive.suffix + ".tmp")
    if tmp_archive.exists():
        tmp_archive.unlink()
    with zipfile.ZipFile(tmp_archive, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        for archive in band_archives:
            zf.write(archive, archive.name)
    tmp_archive.replace(outer_archive)


def human_size(path: Path) -> str:
    size = path.stat().st_size
    units = ["B", "K", "M", "G", "T"]
    value = float(size)
    for unit in units:
        if value < 1024.0 or unit == units[-1]:
            return f"{value:.1f}{unit}" if unit != "B" else f"{int(value)}B"
        value /= 1024.0
    return f"{size}B"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_root", help="CSI root containing frequency directories.")
    parser.add_argument("bundle_name", help="Output zip basename, without .zip.")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output package directory.")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing zip.")
    parser.add_argument("--dry-run", action="store_true", help="Print planned archive layout without writing.")
    parser.add_argument(
        "--keep-weather-suffix",
        action="store_true",
        help="Keep source frequency directory names unchanged inside the zip.",
    )
    parser.add_argument(
        "--compression",
        choices=["store", "deflate"],
        default="store",
        help="Use store for fast archiving of .npz files, or deflate for compression.",
    )
    parser.add_argument("--compression-level", type=int, default=1, help="Deflate compression level.")
    args = parser.parse_args()

    source_root = Path(args.source_root).resolve()
    out_dir = Path(args.out_dir).resolve()
    bundle_dir = out_dir / args.bundle_name
    archive = out_dir / f"{args.bundle_name}.zip"
    items = collect_frequency_dirs(source_root, strip_weather_suffix=not args.keep_weather_suffix)

    total_files = sum(len(files) for _, _, files in items)
    print(f"[Package] source={source_root}")
    print(f"[Package] bundle_dir={bundle_dir}")
    print(f"[Package] output={archive}")
    print(f"[Package] bands={len(items)} csi_npz={total_files}")

    if args.dry_run:
        for band, freq_dir, files in items:
            print(f"[DryRun] {freq_dir.name} -> {band}.zip ({len(files)} files)")
        print(f"[DryRun] outer zip entries: {[band + '.zip' for band, _, _ in items]}")
        return

    prepare_output(bundle_dir, archive, overwrite=args.overwrite)
    compression = zipfile.ZIP_STORED if args.compression == "store" else zipfile.ZIP_DEFLATED
    compression_level = None if args.compression == "store" else args.compression_level

    band_archives: list[Path] = []
    written_files = 0
    for band, freq_dir, files in items:
        band_archive = bundle_dir / f"{band}.zip"
        print(f"[Package] creating {band_archive} source={freq_dir.name} files={len(files)}")
        written_files += write_zip_from_files(
            band_archive,
            files,
            compression=compression,
            compression_level=compression_level,
        )
        band_archives.append(band_archive)

    print(f"[Package] creating outer archive {archive}")
    write_outer_zip(bundle_dir, archive, band_archives)
    print(f"[Package] wrote files={written_files} outer_size={human_size(archive)} archive={archive}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
