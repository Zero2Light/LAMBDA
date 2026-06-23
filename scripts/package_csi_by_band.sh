#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DEFAULT_SOURCE="data_export/example_csi/csi"
SOURCE_ROOT="${1:-$DEFAULT_SOURCE}"
OUT_DIR="${2:-data_export/_packages}"
BUNDLE_NAME="${3:-}"

DRY_RUN="${DRY_RUN:-0}"
OVERWRITE="${OVERWRITE:-0}"
ZIP_LEVEL="${ZIP_LEVEL:-6}"

usage() {
  cat <<'EOF'
Usage:
  scripts/package_csi_by_band.sh [SOURCE_ROOT] [OUT_DIR] [BUNDLE_NAME]

Default:
  SOURCE_ROOT = data_export/example_csi/csi
  OUT_DIR     = data_export/_packages

Environment:
  DRY_RUN=1     Print planned archives without creating them.
  OVERWRITE=1   Replace an existing bundle directory/archive.
  ZIP_LEVEL=6   Compression level passed to zip.

The script recursively finds directories named like f60p0GHz_V under SOURCE_ROOT.
It creates one flat .zip per frequency tag, where csi_*.npz files are stored at
the zip root, then creates one flat outer .zip containing only the per-frequency
.zip files at its root. A manifest is written next to the per-frequency zips but
is not included in the outer archive.

Flat packaging requires exactly one directory per frequency tag under SOURCE_ROOT;
otherwise csi_*.npz names from multiple trajectories would collide.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

resolve_dir() {
  local path="$1"
  if [[ "$path" = /* ]]; then
    printf '%s\n' "$path"
  else
    printf '%s\n' "$ROOT_DIR/$path"
  fi
}

SOURCE_ROOT="$(resolve_dir "$SOURCE_ROOT")"
OUT_DIR="$(resolve_dir "$OUT_DIR")"

if [[ ! -d "$SOURCE_ROOT" ]]; then
  echo "[Error] SOURCE_ROOT does not exist: $SOURCE_ROOT" >&2
  exit 1
fi

source_label="$(basename "$SOURCE_ROOT")"
if [[ "$source_label" == "csi" || "$source_label" == "array_csi" || "$source_label" == "subcarrier_csi" ]]; then
  parent_label="$(basename "$(dirname "$SOURCE_ROOT")")"
  source_label="${parent_label}_${source_label}"
fi
source_label="$(printf '%s' "$source_label" | tr ' /' '__' | tr -cd 'A-Za-z0-9._-')"
timestamp="$(date +%Y%m%d_%H%M%S)"
BUNDLE_NAME="${BUNDLE_NAME:-${source_label}_by_band_${timestamp}}"

bundle_dir="$OUT_DIR/$BUNDLE_NAME"
manifest="$bundle_dir/manifest.txt"
outer_archive="$OUT_DIR/${BUNDLE_NAME}.zip"
legacy_outer_archive="$OUT_DIR/${BUNDLE_NAME}.tar.gz"

if ! command -v zip >/dev/null 2>&1; then
  echo "[Error] zip command not found. Install zip or use a machine with Info-ZIP available." >&2
  exit 1
fi

if [[ -e "$bundle_dir" || -e "$outer_archive" || -e "$legacy_outer_archive" ]]; then
  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[DryRun] Output already exists; OVERWRITE=1 would replace:" >&2
    echo "         $bundle_dir" >&2
    echo "         $outer_archive" >&2
    echo "         $legacy_outer_archive" >&2
  elif [[ "$OVERWRITE" == "1" ]]; then
    rm -rf "$bundle_dir" "$outer_archive" "$legacy_outer_archive"
  else
    echo "[Error] Output already exists. Set OVERWRITE=1 or choose a new BUNDLE_NAME." >&2
    echo "        $bundle_dir" >&2
    echo "        $outer_archive" >&2
    echo "        $legacy_outer_archive" >&2
    exit 1
  fi
fi

declare -A seen=()
bands=()
while IFS= read -r -d '' freq_dir; do
  band="$(basename "$freq_dir")"
  if [[ -z "${seen[$band]:-}" ]]; then
    seen["$band"]=1
    bands+=("$band")
  fi
done < <(find "$SOURCE_ROOT" -type d -name 'f*GHz*' -print0)

if [[ "${#bands[@]}" -eq 0 ]]; then
  echo "[Error] No frequency directories matching f*GHz* found under: $SOURCE_ROOT" >&2
  exit 1
fi

mapfile -t bands < <(printf '%s\n' "${bands[@]}" | sort -V)

echo "[Package] source=$SOURCE_ROOT"
echo "[Package] output=$bundle_dir"
echo "[Package] bands=${bands[*]}"

if [[ "$DRY_RUN" == "1" ]]; then
  for band in "${bands[@]}"; do
    count="$(find "$SOURCE_ROOT" -type d -name "$band" -print | wc -l)"
    npz_count="$(find "$SOURCE_ROOT" -path "*/$band/*" -type f -name 'csi_*.npz' -print | wc -l | tr -d ' ')"
    echo "[DryRun] $band: frequency_dirs=$count csi_npz=$npz_count -> $band.zip"
  done
  echo "[DryRun] outer archive: $outer_archive"
  exit 0
fi

mkdir -p "$bundle_dir"

{
  echo "bundle_name=$BUNDLE_NAME"
  echo "created_at=$(date --iso-8601=seconds)"
  echo "source_root=$SOURCE_ROOT"
  echo "output_dir=$bundle_dir"
  echo
} > "$manifest"

make_flat_zip() {
  local archive="$1"
  local freq_dir="$2"
  (cd "$freq_dir" && find . -maxdepth 1 -type f -name 'csi_*.npz' -printf '%P\n' | sort -V | zip -q "-${ZIP_LEVEL}" "$archive" -@)
}

outer_entries=()
for band in "${bands[@]}"; do
  freq_dirs=()

  while IFS= read -r -d '' freq_dir; do
    freq_dirs+=("$freq_dir")
  done < <(find "$SOURCE_ROOT" -type d -name "$band" -print0 | sort -z)

  freq_dir_count="${#freq_dirs[@]}"
  if [[ "$freq_dir_count" -ne 1 ]]; then
    echo "[Error] Flat packaging requires exactly one directory for $band, found $freq_dir_count." >&2
    echo "        Use a SOURCE_ROOT that points to one CSI set, or choose a non-flat package layout." >&2
    exit 1
  fi

  freq_dir="${freq_dirs[0]}"
  archive="$bundle_dir/${band}.zip"
  npz_count="$(find "$freq_dir" -maxdepth 1 -type f -name 'csi_*.npz' -print | wc -l | tr -d ' ')"
  if [[ "$npz_count" -eq 0 ]]; then
    echo "[Error] No csi_*.npz files found in $freq_dir" >&2
    exit 1
  fi

  echo "[Package] creating $archive"
  make_flat_zip "$archive" "$freq_dir"
  archive_size="$(du -h "$archive" | awk '{print $1}')"
  outer_entries+=("$(basename "$archive")")

  {
    echo "band=$band"
    echo "archive=${band}.zip"
    echo "archive_size=$archive_size"
    echo "frequency_dir_count=$freq_dir_count"
    echo "csi_npz_count=$npz_count"
    echo
  } >> "$manifest"
done

echo "[Package] creating outer archive $outer_archive"
(cd "$bundle_dir" && zip -q "-${ZIP_LEVEL}" "$outer_archive" "${outer_entries[@]}")

echo "[Package] done"
echo "[Package] manifest=$manifest"
echo "[Package] outer=$(du -h "$outer_archive" | awk '{print $1}') $outer_archive"
