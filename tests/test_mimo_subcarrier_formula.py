import unittest

import numpy as np

from lambda_rf.utils.array_csi import (
    C_M_S,
    build_array_csi_fields,
    planar_array_positions,
    steering_vectors,
)
from lambda_rf.utils.subcarrier_csi import (
    build_subcarrier_csi_fields,
    centered_subcarrier_offsets,
)


class MimoSubcarrierFormulaTest(unittest.TestCase):
    def test_array_subcarrier_matches_direct_path_sum_formula(self):
        carrier_frequency = C_M_S
        wavelength = C_M_S / carrier_frequency
        tx_shape = (1, 2)
        rx_shape = (1, 2)
        spacing = 0.5

        a_path = np.asarray([1.0 + 0.25j, 0.5 - 0.75j], dtype=np.complex128)
        tau = np.asarray([0.0, 0.25], dtype=np.float64)
        theta_t = np.asarray([np.pi / 2, np.pi / 2], dtype=np.float64)
        phi_t = np.asarray([0.0, np.pi / 2], dtype=np.float64)
        theta_r = np.asarray([np.pi / 2, np.pi / 2], dtype=np.float64)
        phi_r = np.asarray([np.pi / 2, 0.0], dtype=np.float64)

        arrays = {
            "a_real": a_path.real.astype(np.float32),
            "a_imag": a_path.imag.astype(np.float32),
            "tau": tau,
            "theta_t": theta_t.astype(np.float32),
            "phi_t": phi_t.astype(np.float32),
            "theta_r": theta_r.astype(np.float32),
            "phi_r": phi_r.astype(np.float32),
            "valid": np.ones(a_path.shape, dtype=bool),
            "carrier_frequency": np.asarray(carrier_frequency, dtype=np.float64),
        }

        array_fields = build_array_csi_fields(
            arrays,
            carrier_frequency_hz=carrier_frequency,
            tx_shape=tx_shape,
            rx_shape=rx_shape,
            spacing_wavelengths=spacing,
        )
        arrays.update(array_fields)
        subcarrier_fields = build_subcarrier_csi_fields(
            arrays,
            num_subcarriers=4,
            subcarrier_spacing_hz=1.0,
            input_mode="array",
        )
        actual = subcarrier_fields["h_freq_real"] + 1j * subcarrier_fields["h_freq_imag"]

        tx_pos = planar_array_positions(tx_shape, wavelength, spacing)
        rx_pos = planar_array_positions(rx_shape, wavelength, spacing)
        tx_sv = steering_vectors(tx_pos, theta_t, phi_t, wavelength)
        rx_sv = steering_vectors(rx_pos, theta_r, phi_r, wavelength)
        offsets = centered_subcarrier_offsets(4, 1.0)

        expected = np.zeros((2, 2, 4), dtype=np.complex128)
        for path_idx in range(a_path.size):
            path_mimo = (
                rx_sv[:, np.newaxis, path_idx]
                * np.conjugate(tx_sv[np.newaxis, :, path_idx])
                * a_path[path_idx]
            )
            path_freq = np.exp(-1j * 2.0 * np.pi * offsets * tau[path_idx])
            expected += path_mimo[:, :, np.newaxis] * path_freq[np.newaxis, np.newaxis, :]

        np.testing.assert_allclose(actual, expected, atol=1e-6)


if __name__ == "__main__":
    unittest.main()
