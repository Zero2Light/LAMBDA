import importlib.util
import unittest

import numpy as np

from lambda_rf.utils.subcarrier_csi import centered_subcarrier_offsets


@unittest.skipIf(importlib.util.find_spec("deepmimo") is None, "deepmimo is not installed")
class DeepMimoCompatibilityTest(unittest.TestCase):
    def test_subcarrier_formula_matches_deepmimo_generator_core(self):
        import deepmimo.consts as c
        from deepmimo.generator.channel import _generate_mimo_channel

        alpha = np.asarray([1.0 + 0.25j, 0.5 - 0.75j], dtype=np.complex128)
        tau = np.asarray([0.0, 0.25], dtype=np.float64)
        array_response_product = np.asarray(
            [
                [
                    [[1.0 + 0.0j, 0.0 + 1.0j], [0.0 - 1.0j, 1.0 + 0.0j]],
                    [[0.0 + 1.0j, 1.0 + 0.0j], [1.0 + 0.0j, 0.0 - 1.0j]],
                ]
            ],
            dtype=np.complex64,
        )

        num_subcarriers = 4
        subcarrier_spacing_hz = 1.0
        offsets = centered_subcarrier_offsets(num_subcarriers, subcarrier_spacing_hz)
        expected = np.sum(
            array_response_product[0, :, :, :, np.newaxis]
            * alpha[np.newaxis, np.newaxis, :, np.newaxis]
            * np.exp(-1j * 2.0 * np.pi * tau[:, np.newaxis] * offsets[np.newaxis, :]),
            axis=2,
        )

        ofdm_params = {
            c.PARAMSET_OFDM_SC_NUM: num_subcarriers,
            c.PARAMSET_OFDM_SC_SAMP: (offsets / subcarrier_spacing_hz).astype(int),
            c.PARAMSET_OFDM_BANDWIDTH: num_subcarriers * subcarrier_spacing_hz,
            c.PARAMSET_OFDM_LPF: 0,
        }
        power = (num_subcarriers * np.abs(alpha) ** 2)[np.newaxis, :]
        phase = np.rad2deg(np.angle(alpha))[np.newaxis, :]
        delay = tau[np.newaxis, :]
        doppler = np.zeros_like(delay)

        actual = _generate_mimo_channel(
            array_response_product=array_response_product,
            power=power,
            delay=delay,
            phase=phase,
            doppler=doppler,
            ofdm_params=ofdm_params,
            times=0.0,
            freq_domain=True,
            squeeze_time=True,
            chunk_size=1,
        )[0]

        np.testing.assert_allclose(actual, expected, atol=1e-6)


if __name__ == "__main__":
    unittest.main()
