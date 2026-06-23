from __future__ import annotations

from pathlib import Path

import numpy as np

from lambda_rf import config
from lambda_rf import paths
from lambda_rf.utils.radar import (
    H5RCSModel,
    IMURotationLoader,
    RadarSystem,
    load_csi_paths,
    parse_frame_index,
    parse_shape,
    rotation_matrix_zyx_degrees,
    synthesize_radar_cube,
    virtual_array_positions,
)


def _select_files(csi_dir: Path, start_frame: int | None, limit: int | None, frame_step: int) -> list[Path]:
    files = sorted(csi_dir.glob("csi_*.npz"))
    if start_frame is not None:
        files = [
            path for path in files
            if (parse_frame_index(path, prefix="csi") is not None and parse_frame_index(path, prefix="csi") >= start_frame)
        ]
    if frame_step > 1:
        files = files[::frame_step]
    if limit is not None:
        files = files[: max(0, int(limit))]
    return files


def run(
    csi_dir: str,
    output_dir: str | None = None,
    imu_dir: str | None = None,
    carrier_frequency_hz: float | None = None,
    bandwidth_hz: float | None = None,
    sample_rate_hz: float | None = None,
    chirp_duration_s: float | None = None,
    num_chirps: int | None = None,
    noise_floor_dbm: float | None = None,
    array_shape: str | tuple[int, int] | list[int] | None = None,
    spacing_wavelengths: float | None = None,
    radar_yaw_deg: float | None = None,
    radar_pitch_deg: float | None = None,
    radar_roll_deg: float | None = None,
    add_noise: bool = False,
    skip_existing: bool = False,
    start_frame: int | None = None,
    limit: int | None = None,
    frame_step: int = 1,
) -> None:
    csi_root = Path(csi_dir).expanduser().resolve()
    if not csi_root.is_dir():
        raise FileNotFoundError(f"CSI directory not found: {csi_root}")

    output_root = Path(output_dir).expanduser().resolve() if output_dir else csi_root.parent / "radar_raw" / csi_root.name
    files = _select_files(csi_root, start_frame=start_frame, limit=limit, frame_step=max(1, int(frame_step)))
    if not files:
        raise FileNotFoundError(f"No csi_*.npz files found in {csi_root}")

    if carrier_frequency_hz is None:
        with np.load(files[0], allow_pickle=False) as first_csi:
            carrier_frequency_hz = float(np.asarray(first_csi.get("carrier_frequency", config.CARRIER_FREQUENCY)).reshape(-1)[0])
    f_c = float(carrier_frequency_hz)
    radar_system = RadarSystem(
        f_c=f_c,
        bandwidth=float(bandwidth_hz or config.RADAR_SETTINGS["bandwidth"]),
        sample_rate=float(sample_rate_hz or config.RADAR_SETTINGS["sample_rate"]),
        chirp_duration=float(chirp_duration_s or config.RADAR_SETTINGS["chirp_duration"]),
        num_chirps=int(num_chirps or config.RADAR_SETTINGS["num_chirps"]),
        noise_floor_dbm=float(noise_floor_dbm if noise_floor_dbm is not None else config.RADAR_SETTINGS["noise_floor_dbm"]),
    )
    shape = parse_shape(array_shape or config.RADAR_ARRAY_SHAPE, "array_shape")
    antenna_positions = virtual_array_positions(
        radar_system.f_c,
        shape=shape,
        spacing_wavelengths=config.RADAR_SPACING_WAVELENGTHS if spacing_wavelengths is None else spacing_wavelengths,
    )
    yaw = float(config.RADAR_MOUNT["yaw"] if radar_yaw_deg is None else radar_yaw_deg)
    pitch = float(config.RADAR_MOUNT["pitch"] if radar_pitch_deg is None else radar_pitch_deg)
    roll = float(config.RADAR_MOUNT["roll"] if radar_roll_deg is None else radar_roll_deg)
    radar_world_to_local = rotation_matrix_zyx_degrees(yaw, pitch, roll).T

    imu_loader = IMURotationLoader(imu_dir)
    rcs_model = H5RCSModel(config.RCS_MODEL_PATH)
    output_root.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("[Radar] Generating FMCW radar cubes from released path-level CSI.")
    print(f"[Radar] CSI:     {csi_root}")
    print(f"[Radar] IMU:     {Path(imu_dir).resolve() if imu_dir else 'identity orientation'}")
    print(f"[Radar] Output:  {output_root}")
    print(
        f"[Radar] f_c={radar_system.f_c / 1e9:g} GHz, bandwidth={radar_system.bandwidth / 1e9:g} GHz, "
        f"chirps={radar_system.num_chirps}, samples={radar_system.num_samples}, array={shape}"
    )
    print(f"[Radar] RCS:     AirSim default drone ({config.RCS_MODEL_PATH})")
    print(f"[Radar] Files:   {len(files)}")
    print("=" * 80)

    processed = 0
    skipped = 0
    for csi_path in files:
        frame_idx = parse_frame_index(csi_path, prefix="csi")
        out_name = f"radar_{frame_idx:06d}.npz" if frame_idx is not None else csi_path.name.replace("csi_", "radar_")
        output_path = output_root / out_name
        if skip_existing and output_path.exists():
            skipped += 1
            continue

        csi_data = load_csi_paths(csi_path, fallback_carrier_frequency_hz=radar_system.f_c)
        if csi_data is None:
            skipped += 1
            continue

        cube = synthesize_radar_cube(
            csi_data=csi_data,
            uav_rotation_l2w=imu_loader.get(frame_idx),
            rcs_model=rcs_model,
            radar_system=radar_system,
            antenna_positions_m=antenna_positions,
            radar_world_to_local=radar_world_to_local,
            add_noise=add_noise,
        )

        payload = {
            "radar_data": cube,
            "timestamp": np.asarray(csi_data["timestamp"], dtype=np.float64),
            "radar_params": radar_system.params_array(),
            "radar_bandwidth_hz": np.asarray(radar_system.bandwidth, dtype=np.float64),
            "num_chirps": np.asarray(radar_system.num_chirps, dtype=np.int32),
            "radar_array_shape": np.asarray(shape, dtype=np.int32),
            "radar_array_pos": antenna_positions.astype(np.float32),
            "radar_mount_yaw_pitch_roll_deg": np.asarray([yaw, pitch, roll], dtype=np.float64),
            "source_csi_path": np.asarray(str(csi_path)),
            "rcs_model": np.asarray("airsim_default_drone"),
            "radar_model": np.asarray("fmcw_from_path_level_csi_with_airsim_default_drone_rcs"),
        }
        if csi_data.get("uav_pos") is not None:
            payload["gt_pos"] = np.asarray(csi_data["uav_pos"], dtype=np.float64)
        if csi_data.get("uav_vel") is not None:
            payload["gt_vel"] = np.asarray(csi_data["uav_vel"], dtype=np.float64)

        np.savez(output_path, **payload)
        processed += 1
        if processed == 1 or processed % 100 == 0:
            print(f"[Radar] processed={processed}, latest={output_path.name}")

    print(f"[Radar] Done. processed={processed}, skipped={skipped}, output={output_root}")


def main() -> None:
    run(csi_dir=paths.csi_npz_dir())


if __name__ == "__main__":
    main()
