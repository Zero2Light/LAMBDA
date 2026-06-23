from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate array CSI and subcarrier CSI from existing path-level CSI files.",
    )
    parser.add_argument("--input-dir", required=True, help="Directory containing csi_*.npz files.")
    parser.add_argument("--output-root", required=True, help="Root directory for derived outputs.")
    parser.add_argument("--tx-shape", default="4,4", help="TX array shape, e.g. 4,4.")
    parser.add_argument("--rx-shape", default="1,1", help="RX array shape, e.g. 1,1.")
    parser.add_argument("--profile", default="sub6_30k_1024", help="Subcarrier profile name.")
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    from lambda_rf.generate_array_csi import run as run_array_csi
    from lambda_rf.generate_subcarrier_csi import run as run_subcarrier_csi

    input_dir = Path(args.input_dir)
    output_root = Path(args.output_root)
    array_dir = output_root / "array_csi"
    subcarrier_dir = output_root / "subcarrier_csi"

    run_array_csi(
        input_dir=str(input_dir),
        output_dir=str(array_dir),
        tx_shape=args.tx_shape,
        rx_shape=args.rx_shape,
        spacing_wavelengths=0.5,
        skip_existing=args.skip_existing,
        start_frame=None,
        limit=args.limit,
        tx_orientation_pose=None,
        rx_orientation_pose=None,
    )

    run_subcarrier_csi(
        input_dir=str(array_dir),
        output_dir=str(subcarrier_dir),
        profile=args.profile,
        num_subcarriers=None,
        subcarrier_spacing_hz=None,
        input_mode="array",
        tx_shape=args.tx_shape,
        rx_shape=args.rx_shape,
        skip_existing=args.skip_existing,
        start_frame=None,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()
