import importlib.util
from pathlib import Path
import unittest

import numpy as np

from lambda_rf import config
from lambda_rf.utils.radar import (
    C_M_S,
    ConstantRCSModel,
    H5RCSModel,
    RadarSystem,
    synthesize_radar_cube,
    virtual_array_positions,
)
from lambda_rf.visualize_radar import compute_radar_maps


class RadarUtilityTest(unittest.TestCase):
    def test_default_rcs_asset_is_bundled(self):
        self.assertTrue(Path(config.RCS_MODEL_PATH).is_file())

    @unittest.skipIf(importlib.util.find_spec("h5py") is None, "h5py is not installed")
    def test_bundled_h5_rcs_can_be_sampled(self):
        model = H5RCSModel(config.RCS_MODEL_PATH)
        value = model.get_rcs(theta_deg=45.0, phi_deg=90.0)
        self.assertTrue(np.isfinite(value.real))
        self.assertTrue(np.isfinite(value.imag))

    def test_synthesize_radar_cube_shape(self):
        radar = RadarSystem(
            f_c=C_M_S,
            bandwidth=4.0,
            sample_rate=8.0,
            chirp_duration=1.0,
            num_chirps=4,
        )
        csi_data = {
            "a": np.asarray([1.0 + 0.0j]),
            "tau": np.asarray([0.0]),
            "doppler": np.asarray([0.0]),
            "theta_r": np.asarray([np.pi / 2.0]),
            "phi_r": np.asarray([0.0]),
            "theta_t": np.asarray([np.pi / 2.0]),
            "phi_t": np.asarray([0.0]),
        }
        ant_pos = virtual_array_positions(radar.f_c, shape=(1, 2), spacing_wavelengths=0.5)

        cube = synthesize_radar_cube(
            csi_data=csi_data,
            uav_rotation_l2w=np.eye(3),
            rcs_model=ConstantRCSModel(1.0),
            radar_system=radar,
            antenna_positions_m=ant_pos,
        )

        self.assertEqual(cube.shape, (2, 4, 8))
        self.assertEqual(cube.dtype, np.complex64)

    def test_compute_radar_maps_shapes(self):
        radar_params = np.asarray([C_M_S, 4.0, 8.0, 1.0, 8.0], dtype=np.float64)
        cube = np.ones((4, 4, 8), dtype=np.complex64)

        maps = compute_radar_maps(
            cube=cube,
            radar_params=radar_params,
            array_shape=(2, 2),
            angle_fft_size=8,
            remove_clutter=False,
        )

        self.assertEqual(maps["rd_db"].shape, (4, 4))
        self.assertEqual(maps["ra_db"].shape, (8, 4))
        self.assertEqual(maps["re_db"].shape, (8, 4))


if __name__ == "__main__":
    unittest.main()
