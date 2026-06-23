from __future__ import annotations


def ue_to_sionna(x_ue_cm: float, y_ue_cm: float, z_ue_cm: float):
    import mitsuba as mi

    x_s = x_ue_cm * 0.01
    y_s = y_ue_cm * 0.01
    z_s = z_ue_cm * 0.01
    return mi.Point3f(float(x_s), float(y_s), float(z_s))


def point3f_to_xyz(p):
    return float(p.x[0]), float(p.y[0]), float(p.z[0])
