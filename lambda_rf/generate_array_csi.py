from __future__ import annotations

from pathlib import Path

from lambda_rf import config
from lambda_rf import paths
from lambda_rf.utils.array_csi import (
    expand_csi_npz,
    load_rotation_matrix_from_pose_json,
    validate_array_shape,
)


def parse_shape(value: str | tuple[int, int] | list[int] | None, default: tuple[int, int]) -> tuple[int, int]:
    if value is None:
        return validate_array_shape(default, "array_shape")
    if isinstance(value, str):
        parts = [part.strip() for part in value.lower().replace("x", ",").split(",") if part.strip()]
        if len(parts) != 2:
            raise ValueError(f"Invalid array shape {value!r}; expected ROWS,COLS or ROWSxCOLS")
        return validate_array_shape((int(parts[0]), int(parts[1])), "array_shape")
    return validate_array_shape(value, "array_shape")


def _frame_index(path: Path) -> int | None:
    try:
        return int(path.stem.split("_")[-1])
    except ValueError:
        return None


def _expand_pose_path(path_value: str) -> Path:
    variables = {
        "SERVER_ROOT": str(config.SERVER_ROOT),
        "SIONNART_ROOT": str(config.SIONNART_ROOT),
        "PROJECT_ROOT": str(config.PROJECT_ROOT),
        "LAMBDA_ROOT": str(config.LAMBDA_ROOT),
    }
    expanded = str(path_value)
    for name, replacement in variables.items():
        expanded = expanded.replace("${" + name + "}", replacement)
    return Path(expanded).expanduser().resolve()


def _sibling_array_output_dir(input_root: Path, rx_shape: tuple[int, int], tx_shape: tuple[int, int]) -> Path:
    parts = list(input_root.parts)
    for idx, part in enumerate(parts):
        if part.startswith("csi_rt_"):
            parts[idx] = "array_" + part
            return Path(*parts) / paths.array_shape_tag(rx_shape=rx_shape, tx_shape=tx_shape)
        if part == "csi":
            parts[idx] = "array_csi"
            return Path(*parts) / paths.array_shape_tag(rx_shape=rx_shape, tx_shape=tx_shape)
    return input_root.parent / "array_csi" / input_root.name / paths.array_shape_tag(
        rx_shape=rx_shape,
        tx_shape=tx_shape,
    )


def run(
    input_dir: str | None = None,
    output_dir: str | None = None,
    tx_shape: str | tuple[int, int] | list[int] | None = None,
    rx_shape: str | tuple[int, int] | list[int] | None = None,
    spacing_wavelengths: float = 0.5,
    skip_existing: bool = False,
    start_frame: int | None = None,
    limit: int | None = None,
    tx_orientation_pose: str | None = None,
    rx_orientation_pose: str | None = None,
) -> None:
    tx_shape_tuple = parse_shape(tx_shape, config.TX_ARRAY_SHAPE)
    rx_shape_tuple = parse_shape(rx_shape, config.RX_ARRAY_SHAPE)

    input_root = Path(input_dir or paths.csi_npz_dir()).resolve()
    if output_dir:
        output_root = Path(output_dir).resolve()
    elif input_dir:
        output_root = _sibling_array_output_dir(input_root, rx_shape_tuple, tx_shape_tuple).resolve()
    else:
        output_root = Path(
            paths.array_csi_npz_dir(rx_shape=rx_shape_tuple, tx_shape=tx_shape_tuple)
        ).resolve()

    if not input_root.exists():
        raise FileNotFoundError(f"Input CSI directory not found: {input_root}")

    tx_rotation = None
    rx_rotation = None
    tx_orientation_source = None
    rx_orientation_source = None
    if tx_orientation_pose is None and config.TX_POSE_PATH:
        tx_orientation_pose = config.TX_POSE_PATH
    if tx_orientation_pose:
        tx_orientation_path = _expand_pose_path(tx_orientation_pose)
        tx_rotation = load_rotation_matrix_from_pose_json(tx_orientation_path)
        tx_orientation_source = str(tx_orientation_path)
    if rx_orientation_pose:
        rx_orientation_path = _expand_pose_path(rx_orientation_pose)
        rx_rotation = load_rotation_matrix_from_pose_json(rx_orientation_path)
        rx_orientation_source = str(rx_orientation_path)

    csi_files = sorted(input_root.glob("csi_*.npz"))
    if start_frame is not None:
        csi_files = [path for path in csi_files if (_frame_index(path) is not None and _frame_index(path) >= start_frame)]
    if limit is not None:
        csi_files = csi_files[: max(0, int(limit))]
    if not csi_files:
        raise FileNotFoundError(f"No csi_*.npz files found in {input_root}")

    output_root.mkdir(parents=True, exist_ok=True)
    print("=" * 80)
    print("[Array CSI] Expanding single-link CSI with far-field steering.")
    print(f"[Array CSI] Input:   {input_root}")
    print(f"[Array CSI] Output:  {output_root}")
    print(f"[Array CSI] TX shape={tx_shape_tuple}, RX shape={rx_shape_tuple}, spacing={spacing_wavelengths} lambda")
    print(f"[Array CSI] TX orientation: {tx_orientation_source or 'identity/global y-z plane'}")
    print(f"[Array CSI] RX orientation: {rx_orientation_source or 'identity/global y-z plane'}")
    print(f"[Array CSI] Files:   {len(csi_files)}")
    print("=" * 80)

    processed = 0
    skipped = 0
    for input_path in csi_files:
        output_path = output_root / input_path.name
        if skip_existing and output_path.exists():
            skipped += 1
            continue

        expand_csi_npz(
            input_path=input_path,
            output_path=output_path,
            tx_shape=tx_shape_tuple,
            rx_shape=rx_shape_tuple,
            spacing_wavelengths=spacing_wavelengths,
            tx_rotation_matrix=tx_rotation,
            rx_rotation_matrix=rx_rotation,
            tx_orientation_source=tx_orientation_source,
            rx_orientation_source=rx_orientation_source,
        )
        processed += 1
        if processed == 1 or processed % 100 == 0:
            print(f"[Array CSI] processed={processed}, latest={output_path.name}")

    print(f"[Array CSI] Done. processed={processed}, skipped={skipped}, output={output_root}")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
