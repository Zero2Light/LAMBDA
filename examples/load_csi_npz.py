from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect one LAMBDA path-level CSI NPZ file.")
    parser.add_argument("npz_path", help="Path to csi_*.npz.")
    parser.add_argument("--top", type=int, default=5, help="Number of strongest paths to print.")
    return parser.parse_args()


def _field(data: np.lib.npyio.NpzFile, name: str, default=None):
    return data[name] if name in data.files else default


def main() -> None:
    args = parse_args()
    npz_path = Path(args.npz_path)
    if not npz_path.is_file():
        raise FileNotFoundError(npz_path)

    with np.load(npz_path, allow_pickle=True) as data:
        a_real = _field(data, "a_real")
        a_imag = _field(data, "a_imag")
        tau = _field(data, "tau", np.array([]))
        doppler = _field(data, "doppler", np.array([]))
        theta_t = _field(data, "theta_t")
        phi_t = _field(data, "phi_t")
        theta_r = _field(data, "theta_r")
        phi_r = _field(data, "phi_r")

        print(f"File: {npz_path}")
        print(f"Fields: {', '.join(data.files)}")
        print(f"Detected paths: {len(tau)}")
        if doppler.size:
            print(f"Max Doppler shift: {np.max(np.abs(doppler)):.3f} Hz")

        if a_real is not None and a_imag is not None:
            complex_gain = np.asarray(a_real).reshape(-1) + 1j * np.asarray(a_imag).reshape(-1)
            order = np.argsort(np.abs(complex_gain))[::-1]
            for rank, idx in enumerate(order[: args.top], start=1):
                delay = float(np.asarray(tau).reshape(-1)[idx]) if len(tau) > idx else float("nan")
                print(
                    f"path {rank}: index={idx}, |a|={abs(complex_gain[idx]):.6e}, "
                    f"delay={delay:.6e} s"
                )

        if theta_t is not None and phi_t is not None:
            print("AoD theta/phi arrays are available.")
        if theta_r is not None and phi_r is not None:
            print("AoA theta/phi arrays are available.")


if __name__ == "__main__":
    main()

