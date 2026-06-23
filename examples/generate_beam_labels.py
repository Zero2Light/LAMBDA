from __future__ import annotations

import argparse
import csv
import glob
from pathlib import Path

import numpy as np


C = 299_792_458.0


def parse_shape(value: str) -> tuple[int, int]:
    parts = value.replace("x", ",").split(",")
    if len(parts) != 2:
        raise argparse.ArgumentTypeError("shape must be ROWS,COLS, for example 8,8")
    rows, cols = int(parts[0]), int(parts[1])
    if rows <= 0 or cols <= 0:
        raise argparse.ArgumentTypeError("shape values must be positive")
    return rows, cols


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate DFT-codebook beam labels from LAMBDA path-level CSI files.",
    )
    parser.add_argument("--input-dir", required=True, help="Directory containing csi_*.npz files.")
    parser.add_argument("--output-csv", required=True, help="Output CSV path.")
    parser.add_argument("--carrier-frequency", type=float, default=4.9e9, help="Carrier frequency in Hz.")
    parser.add_argument("--array-shape", type=parse_shape, default=(8, 8), help="TX UPA shape, e.g. 8,8.")
    parser.add_argument(
        "--codebook-shape",
        type=parse_shape,
        default=(16, 16),
        help="Oversampled DFT codebook shape, e.g. 16,16.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Optional maximum number of files.")
    return parser.parse_args()


def upa_steering_vector(theta: float, phi: float, rows: int, cols: int) -> np.ndarray:
    row_idx = np.arange(rows)
    col_idx = np.arange(cols)
    u = np.sin(theta) * np.cos(phi)
    v = np.sin(theta) * np.sin(phi)
    a_row = np.exp(1j * np.pi * row_idx * u)
    a_col = np.exp(1j * np.pi * col_idx * v)
    return np.kron(a_row, a_col)


def dft_codebook(num_ant: int, num_beams: int) -> np.ndarray:
    ant_idx = np.arange(num_ant)
    beam_idx = np.arange(num_beams)
    return np.exp(1j * 2.0 * np.pi * np.outer(ant_idx, beam_idx) / num_beams) / np.sqrt(num_ant)


def upa_dft_codebook(rows: int, cols: int, beam_rows: int, beam_cols: int) -> np.ndarray:
    return np.kron(dft_codebook(rows, beam_rows), dft_codebook(cols, beam_cols))


def channel_from_paths(npz_path: Path, carrier_frequency: float, array_shape: tuple[int, int]) -> np.ndarray:
    rows, cols = array_shape
    h = np.zeros(rows * cols, dtype=np.complex128)

    with np.load(npz_path, allow_pickle=True) as data:
        gains = (data["a_real"] + 1j * data["a_imag"]).reshape(-1)
        theta_t = data["theta_t"].reshape(-1)
        phi_t = data["phi_t"].reshape(-1)
        tau = data["tau"].reshape(-1)

    for gain, theta, phi, delay in zip(gains, theta_t, phi_t, tau):
        delay_phase = np.exp(-1j * 2.0 * np.pi * carrier_frequency * delay)
        h += gain * delay_phase * upa_steering_vector(theta, phi, rows, cols)
    return h


def best_beam(channel: np.ndarray, codebook: np.ndarray) -> tuple[int, float]:
    response = codebook.conj().T @ channel
    powers = np.abs(response) ** 2
    label = int(np.argmax(powers))
    return label, float(powers[label])


def main() -> None:
    args = parse_args()
    input_dir = Path(args.input_dir)
    files = [Path(p) for p in sorted(glob.glob(str(input_dir / "csi_*.npz")))]
    if args.limit is not None:
        files = files[: args.limit]
    if not files:
        raise FileNotFoundError(f"No csi_*.npz files found in {input_dir}")

    rows, cols = args.array_shape
    beam_rows, beam_cols = args.codebook_shape
    codebook = upa_dft_codebook(rows, cols, beam_rows, beam_cols)

    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["filename", "beam_index", "received_power"])
        writer.writeheader()
        for npz_path in files:
            h = channel_from_paths(npz_path, args.carrier_frequency, args.array_shape)
            beam_index, received_power = best_beam(h, codebook)
            writer.writerow(
                {
                    "filename": npz_path.name,
                    "beam_index": beam_index,
                    "received_power": received_power,
                }
            )

    print(f"Wrote {len(files)} labels to {output_csv}")


if __name__ == "__main__":
    main()
