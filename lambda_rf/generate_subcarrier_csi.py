from __future__ import annotations

from pathlib import Path

import numpy as np

from lambda_rf import config
from lambda_rf import paths
from lambda_rf.generate_array_csi import parse_shape
from lambda_rf.utils.subcarrier_csi import expand_subcarrier_npz, infer_input_mode, validate_subcarrier_config


def _frame_index(path: Path) -> int | None:
    try:
        return int(path.stem.split("_")[-1])
    except ValueError:
        return None


def _resolve_profile(
    profile_name: str | None,
    num_subcarriers: int | None,
    subcarrier_spacing_hz: float | None,
) -> dict:
    has_override = num_subcarriers is not None or subcarrier_spacing_hz is not None
    if profile_name is not None or not (num_subcarriers is not None and subcarrier_spacing_hz is not None):
        profile = config.get_subcarrier_profile(profile_name)
        resolved_name = profile["name"]
    else:
        profile = {
            "num_subcarriers": int(num_subcarriers),
            "subcarrier_spacing_hz": float(subcarrier_spacing_hz),
        }
        resolved_name = None

    if num_subcarriers is not None:
        profile["num_subcarriers"] = int(num_subcarriers)
    if subcarrier_spacing_hz is not None:
        profile["subcarrier_spacing_hz"] = float(subcarrier_spacing_hz)

    num, spacing = validate_subcarrier_config(
        profile["num_subcarriers"],
        profile["subcarrier_spacing_hz"],
    )
    profile["num_subcarriers"] = num
    profile["subcarrier_spacing_hz"] = spacing
    profile["profile_name"] = resolved_name if not has_override else None
    profile["profile_tag"] = paths.subcarrier_profile_tag(
        profile_name=profile["profile_name"],
        num_subcarriers=num,
        subcarrier_spacing_hz=spacing,
    )
    return profile


def _load_first_file_mode(input_path: Path, requested_mode: str) -> tuple[str, tuple[int, int] | None, tuple[int, int] | None]:
    with np.load(input_path, allow_pickle=False) as data:
        arrays = {key: data[key] for key in data.files}

    mode = infer_input_mode(arrays, input_mode=requested_mode)
    if mode != "array":
        return mode, None, None

    rx_shape = tuple(int(x) for x in arrays["rx_array_shape"]) if "rx_array_shape" in arrays else None
    tx_shape = tuple(int(x) for x in arrays["tx_array_shape"]) if "tx_array_shape" in arrays else None
    return mode, rx_shape, tx_shape


def _input_tag(mode: str, rx_shape: tuple[int, int] | None, tx_shape: tuple[int, int] | None) -> str:
    if mode == "array":
        if rx_shape is None or tx_shape is None:
            return "array"
        return paths.array_shape_tag(rx_shape=rx_shape, tx_shape=tx_shape)
    return "single"


def _sibling_subcarrier_output_dir(input_root: Path, input_tag: str, profile_tag: str) -> Path:
    parts = list(input_root.parts)
    for idx, part in enumerate(parts):
        if part.startswith("csi_rt_"):
            parts[idx] = "subcarrier_" + part
            base = Path(*parts)
            return base / input_tag / profile_tag
        if part.startswith("array_csi_rt_"):
            parts[idx] = "subcarrier_csi_rt_" + part.removeprefix("array_csi_rt_")
            base = Path(*parts)
            return base / profile_tag if base.name == input_tag else base / input_tag / profile_tag
        if part == "csi":
            parts[idx] = "subcarrier_csi"
            base = Path(*parts)
            return base / input_tag / profile_tag
        if part == "array_csi":
            parts[idx] = "subcarrier_csi"
            base = Path(*parts)
            return base / profile_tag if base.name == input_tag else base / input_tag / profile_tag
    return input_root.parent / "subcarrier_csi" / input_root.name / input_tag / profile_tag


def run(
    input_dir: str | None = None,
    output_dir: str | None = None,
    profile: str | None = None,
    num_subcarriers: int | None = None,
    subcarrier_spacing_hz: float | None = None,
    input_mode: str = "auto",
    tx_shape: str | tuple[int, int] | list[int] | None = None,
    rx_shape: str | tuple[int, int] | list[int] | None = None,
    skip_existing: bool = False,
    start_frame: int | None = None,
    limit: int | None = None,
) -> None:
    requested_mode = str(input_mode).lower()
    profile_cfg = _resolve_profile(profile, num_subcarriers, subcarrier_spacing_hz)

    tx_shape_tuple = parse_shape(tx_shape, config.TX_ARRAY_SHAPE)
    rx_shape_tuple = parse_shape(rx_shape, config.RX_ARRAY_SHAPE)

    if input_dir:
        input_root = Path(input_dir).resolve()
    elif requested_mode == "array":
        input_root = Path(paths.array_csi_npz_dir(rx_shape=rx_shape_tuple, tx_shape=tx_shape_tuple)).resolve()
    else:
        input_root = Path(paths.csi_npz_dir()).resolve()

    if not input_root.exists():
        hint = ""
        if requested_mode == "array":
            hint = " Run array-csi first or pass --input-dir to an existing array CSI directory."
        raise FileNotFoundError(f"Input CSI directory not found: {input_root}.{hint}")

    csi_files = sorted(input_root.glob("csi_*.npz"))
    if start_frame is not None:
        csi_files = [path for path in csi_files if (_frame_index(path) is not None and _frame_index(path) >= start_frame)]
    if limit is not None:
        csi_files = csi_files[: max(0, int(limit))]
    if not csi_files:
        raise FileNotFoundError(f"No csi_*.npz files found in {input_root}")

    effective_mode, file_rx_shape, file_tx_shape = _load_first_file_mode(csi_files[0], requested_mode)
    output_input_tag = _input_tag(
        effective_mode,
        file_rx_shape or rx_shape_tuple,
        file_tx_shape or tx_shape_tuple,
    )

    if output_dir:
        output_root = Path(output_dir).resolve()
    elif input_dir:
        output_root = _sibling_subcarrier_output_dir(
            input_root=input_root,
            input_tag=output_input_tag,
            profile_tag=profile_cfg["profile_tag"],
        ).resolve()
    else:
        output_root = Path(
            paths.subcarrier_csi_npz_dir(
                input_tag=output_input_tag,
                profile_name=profile_cfg["profile_name"],
                num_subcarriers=profile_cfg["num_subcarriers"],
                subcarrier_spacing_hz=profile_cfg["subcarrier_spacing_hz"],
            )
        ).resolve()

    output_root.mkdir(parents=True, exist_ok=True)
    print("=" * 80)
    print("[Subcarrier CSI] Building OFDM-like frequency-domain CSI from path delays.")
    print(f"[Subcarrier CSI] Input:   {input_root}")
    print(f"[Subcarrier CSI] Output:  {output_root}")
    print(f"[Subcarrier CSI] Mode:    requested={requested_mode}, effective={effective_mode}")
    print(
        f"[Subcarrier CSI] Profile: {profile_cfg['profile_tag']} | "
        f"N={profile_cfg['num_subcarriers']}, df={profile_cfg['subcarrier_spacing_hz']} Hz"
    )
    print(f"[Subcarrier CSI] Files:   {len(csi_files)}")
    print("=" * 80)

    processed = 0
    skipped = 0
    for input_path in csi_files:
        output_path = output_root / input_path.name
        if skip_existing and output_path.exists():
            skipped += 1
            continue

        expand_subcarrier_npz(
            input_path=input_path,
            output_path=output_path,
            num_subcarriers=profile_cfg["num_subcarriers"],
            subcarrier_spacing_hz=profile_cfg["subcarrier_spacing_hz"],
            input_mode=requested_mode,
            profile_name=profile_cfg["profile_tag"],
        )
        processed += 1
        if processed == 1 or processed % 100 == 0:
            print(f"[Subcarrier CSI] processed={processed}, latest={output_path.name}")

    print(f"[Subcarrier CSI] Done. processed={processed}, skipped={skipped}, output={output_root}")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
