# Configuration

`configs/scenarios.json` provides defaults for the public RF utilities. It is
mainly used for path conventions, array dimensions, frequency tags, weather
tags, subcarrier profiles, radar settings, and the bundled AirSim drone RCS
model.

Most commands can be run directly with explicit `--input-dir` and `--output-dir`
paths. Use the config when you want reproducible naming across multiple runs.

## Loading Rules

The config has three top-level keys:

```json
{
  "default_scenario": "example_csi",
  "common": {},
  "scenarios": {}
}
```

`common` provides defaults. Each entry under `scenarios` deep-merges over those
defaults. Runtime overrides are available through:

```bash
python -m lambda_rf --config path/to/scenarios.json list-scenarios
python -m lambda_rf --config path/to/scenarios.json array-csi --scenario example_csi --input-dir path/to/csi
```

## Paths

Supported path variables:

| Variable | Meaning |
| --- | --- |
| `${SERVER_ROOT}` | Repository root. |
| `${LAMBDA_ROOT}` | Defaults to `${SERVER_ROOT}` and can be overridden by `LAMBDA_ROOT`. |
| `${SIONNART_ROOT}` | Parent of the repository root, kept for compatibility with local layouts. |
| `${PROJECT_ROOT}` | Parent of `${SIONNART_ROOT}`, kept for compatibility with local layouts. |

Path fields used by the public utilities:

| Field | Meaning |
| --- | --- |
| `output_root` | Root used when a command constructs default output paths. |
| `scene_name` | Dataset family or scene group shown in generated paths. |
| `scenario_name` | Scenario label shown in generated paths. |
| `data_weather` | Condition layer, for example `Sunny`, `Rainy`, `Foggy`, `Snowy`, or `Night`. |
| `station_name` | Base-station label. |
| `trajectory_name` | Trajectory label. |
| `tx_pose_path` | Optional pose JSON used as the default TX array orientation source. |

The default utility path convention is:

```text
<output_root>/<scene_name>/<scenario_name>/<data_weather>/<station_name>/<trajectory_name>/
  csi/<freq_pol_weather_tag>/
  array_csi/<freq_pol_weather_tag>/<array_shape_tag>/
  subcarrier_csi/<freq_pol_weather_tag>/<input_tag>/<profile>/
  radar_raw/<freq_pol_weather_tag>/
  radar_vis/<freq_pol_weather_tag>/
```

When `--input-dir` is passed, array and subcarrier outputs are written as
sibling directories unless `--output-dir` is also passed.

## Frequency And Weather Tags

Frequency/polarization tags use:

```text
f<GHz with p decimal>GHz_<POL>
```

Examples:

```text
f4p9GHz_V
f60p0GHz_V
f77p0GHz_V
```

Clear-condition CSI keeps the short frequency tag. Rain, fog, and snow tags add
the configured weather suffix:

```text
f60p0GHz_V_rain_R10p0mmh_gas_p676
f60p0GHz_V_fog_M0p1gpm3_gas_p676
f60p0GHz_V_snow_gunn_east_dry_R2p0mmh_lwe_gas_p676
```

## Array CSI

`array-csi` expands released path-level CSI into far-field array/MIMO CSI.

```bash
python -m lambda_rf array-csi \
  --input-dir path/to/csi/f60p0GHz_V \
  --output-dir path/to/array_csi/f60p0GHz_V/rx1x1_tx4x4 \
  --tx-shape 4,4 \
  --rx-shape 1,1
```

Useful options:

| Option | Meaning |
| --- | --- |
| `--tx-shape ROWS,COLS` | TX planar array shape. |
| `--rx-shape ROWS,COLS` | RX planar array shape. |
| `--spacing-wavelengths` | Element spacing in carrier wavelengths, default `0.5`. |
| `--tx-orientation-pose` | Pose JSON whose quaternion rotates TX local array coordinates into the world frame. |
| `--rx-orientation-pose` | Pose JSON whose quaternion rotates RX local array coordinates into the world frame. |
| `--start-frame` | Only process frames at or after this index. |
| `--limit` | Maximum number of files to process. |
| `--skip-existing` | Skip existing output files. |

Added NPZ fields:

| Field | Shape | Meaning |
| --- | --- | --- |
| `a_mimo_real` / `a_mimo_imag` | `(rx_ant, tx_ant, path)` | Array CSI coefficients. |
| `rx_array_pos` / `tx_array_pos` | `(num_ant, 3)` | World-frame element offsets, in meters. |
| `rx_array_pos_local` / `tx_array_pos_local` | `(num_ant, 3)` | Centered local y-z plane element offsets, in meters. |
| `rx_array_rotation` / `tx_array_rotation` | `(3, 3)` | Local-to-world rotation matrix. |
| `rx_array_shape` / `tx_array_shape` | `(2,)` | `[rows, cols]`. |
| `array_spacing_wavelengths` | scalar | Element spacing in wavelengths. |
| `source_csi_path` | scalar string | Source path-level CSI file path. |

## Subcarrier CSI

`subcarrier-csi` builds OFDM-like frequency-domain CSI from path delays and
path coefficients.

Single-link input:

```bash
python -m lambda_rf subcarrier-csi \
  --input-dir path/to/csi/f60p0GHz_V \
  --output-dir path/to/subcarrier_csi/f60p0GHz_V/single/sub6_30k_1024 \
  --profile sub6_30k_1024
```

Array/MIMO input:

```bash
python -m lambda_rf subcarrier-csi \
  --input-dir path/to/array_csi/f60p0GHz_V/rx1x1_tx4x4 \
  --output-dir path/to/subcarrier_csi/f60p0GHz_V/rx1x1_tx4x4/sub6_30k_1024 \
  --input-mode array \
  --profile sub6_30k_1024
```

Default profiles:

| Profile | Subcarriers | Spacing | Nominal bandwidth |
| --- | ---: | ---: | ---: |
| `lband_15k_1024` | 1024 | 15 kHz | 15.36 MHz |
| `sub6_30k_1024` | 1024 | 30 kHz | 30.72 MHz |
| `sub6_60k_512` | 512 | 60 kHz | 30.72 MHz |
| `mmwave_120k_512` | 512 | 120 kHz | 61.44 MHz |
| `mmwave_240k_256` | 256 | 240 kHz | 61.44 MHz |

You can override profiles from the command line:

```bash
python -m lambda_rf subcarrier-csi \
  --input-dir path/to/csi/f4p9GHz_V \
  --num-subcarriers 2048 \
  --subcarrier-spacing 30000
```

Added NPZ fields:

| Field | Shape | Meaning |
| --- | --- | --- |
| `h_freq_real` / `h_freq_imag` | `(subcarrier,)`, `(rx_ant, tx_ant, subcarrier)`, or compatible batch shape | Frequency-domain CSI. |
| `subcarrier_frequencies_hz` | `(subcarrier,)` | Baseband frequency offset of each subcarrier. |
| `subcarrier_spacing_hz` | scalar | Subcarrier spacing. |
| `num_subcarriers` | scalar | Number of subcarriers. |
| `subcarrier_input_mode` | scalar string | `single` or `array`. |
| `subcarrier_profile` | scalar string | Profile name or generated profile tag. |

## CSI Reader

```bash
python -m lambda_rf read-csi path/to/csi_000000.npz
python -m lambda_rf read-csi path/to/csi_000000.npz --top 0 --csv paths.csv
```

The reader prints path count, strongest paths, delay, angles, and available NPZ
fields. The CSV export is useful for quick inspection and plotting.

## Radar Signal Generation

`radar` synthesizes FMCW radar cubes from released path-level CSI files. It does
not require scene XML files. It always uses the bundled AirSim default-drone RCS
model:

```text
assets/default_drone_rcs.h5
```

Install radar dependencies first:

```bash
pip install -e ".[radar]"
```

Generate radar raw files:

```bash
python -m lambda_rf radar \
  --input-dir path/to/csi/f60p0GHz_V \
  --output-dir path/to/radar_raw/f60p0GHz_V \
  --imu-dir path/to/imu
```

Useful options:

| Option | Meaning |
| --- | --- |
| `--imu-dir` | Optional directory containing `imu_*.json` orientation files. Identity orientation is used when omitted. |
| `--bandwidth` | FMCW bandwidth in Hz. |
| `--sample-rate` | ADC sample rate in Hz. |
| `--chirp-duration` | Chirp duration in seconds. |
| `--num-chirps` | Number of chirps per frame. |
| `--array-shape` | Radar virtual array shape, default `4,4`. |
| `--radar-yaw`, `--radar-pitch`, `--radar-roll` | Radar mount orientation in degrees. |

Output NPZ fields include:

| Field | Shape | Meaning |
| --- | --- | --- |
| `radar_data` | `(ant, chirp, range_bin)` | Complex range-FFT radar cube. |
| `radar_params` | `(5,)` | `[f_c, slope, sample_rate, chirp_duration, num_samples]`. |
| `radar_array_pos` | `(ant, 3)` | Virtual array element positions in meters. |
| `radar_array_shape` | `(2,)` | `[rows, cols]`. |
| `rcs_model` | scalar string | `airsim_default_drone`. |
| `source_csi_path` | scalar string | Source CSI file path. |
| `gt_pos` / `gt_vel` | `(3,)` when present | Ground-truth target position and velocity copied from CSI. |

## Radar Visualization

`radar-vis` renders Range-Doppler, Range-Azimuth, and Range-Elevation images
from `radar_*.npz` files:

```bash
python -m lambda_rf radar-vis \
  --input-dir path/to/radar_raw/f60p0GHz_V \
  --output-dir path/to/radar_vis/f60p0GHz_V
```

It writes:

```text
RD/frame_000000_RD.png
RA/frame_000000_RA.png
RE/frame_000000_RE.png
```

GT overlay is available when radar files include `gt_pos/gt_vel`:

```bash
python -m lambda_rf radar-vis \
  --input-dir path/to/radar_raw/f60p0GHz_V \
  --output-dir path/to/radar_vis/f60p0GHz_V \
  --show-gt \
  --bs-position 0,0,0
```
