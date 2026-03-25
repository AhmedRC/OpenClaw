"""
Reinforced Concrete Column Design per ACI 318-19
=================================================

This script designs rectangular and circular reinforced concrete columns
per ACI 318-19 Building Code Requirements for Structural Concrete.

Usage
-----
  python rc_column_design.py               # Run built-in examples
  python rc_column_design.py --help        # Show CLI help

Output
------
  rc_column_design.xlsx   — Excel workbook with Input, Results, and
                            Interaction Diagram sheets for each column.

References
----------
  ACI 318-19: Building Code Requirements for Structural Concrete
  ACI 318R-19: Commentary on Building Code Requirements
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ── Optional Excel / plot dependencies ───────────────────────────────────────
try:
    import openpyxl
    from openpyxl import Workbook
    from openpyxl.chart import ScatterChart, Reference, Series
    from openpyxl.chart.series import SeriesLabel
    from openpyxl.styles import (
        Alignment,
        Border,
        Font,
        GradientFill,
        PatternFill,
        Side,
    )
    from openpyxl.utils import get_column_letter

    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

try:
    import matplotlib.pyplot as plt
    import numpy as np

    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False

# =============================================================================
# ACI 318-19 CONSTANTS
# =============================================================================

PHI_TIED = 0.65      # Compression-controlled – tied column  (Table 21.2.2)
PHI_SPIRAL = 0.75    # Compression-controlled – spiral column (Table 21.2.2)
PHI_TENSION = 0.90   # Tension-controlled section              (Table 21.2.2)

RHO_MIN = 0.01       # Minimum longitudinal steel ratio  (Section 10.6.1.1)
RHO_MAX = 0.08       # Maximum longitudinal steel ratio  (Section 10.6.1.1)

EPSILON_CU = 0.003   # Ultimate concrete compressive strain   (Section 22.2.2.1)
ES = 29_000_000      # Modulus of elasticity of steel, psi    (Section 20.2.2.2)

EPSILON_TY = 0.002   # Net tensile strain at compression-controlled limit
EPSILON_TT = 0.005   # Net tensile strain at tension-controlled limit

# =============================================================================
# US STANDARD REBAR DATABASE
# (bar number: (diameter [in], area [in²]))
# =============================================================================

REBAR_DB: dict[int, tuple[float, float]] = {
    3:  (0.375, 0.11),
    4:  (0.500, 0.20),
    5:  (0.625, 0.31),
    6:  (0.750, 0.44),
    7:  (0.875, 0.60),
    8:  (1.000, 0.79),
    9:  (1.128, 1.00),
    10: (1.270, 1.27),
    11: (1.410, 1.56),
    14: (1.693, 2.25),
    18: (2.257, 4.00),
}

# =============================================================================
# INPUT / RESULT DATA CLASSES
# =============================================================================


@dataclass
class ColumnInput:
    """All user-supplied parameters for a single column design case."""

    label: str = "Column C1"

    # ── Geometry ──────────────────────────────────────────────────────────────
    column_type: str = "rectangular"   # "rectangular" | "circular"
    b: float = 16.0    # Width (rect) or diameter (circ), in
    h: float = 16.0    # Depth (rect only), in
    Lu: float = 120.0  # Unsupported (clear) length, in
    k: float = 1.0     # Effective-length factor
    braced: bool = True  # True → non-sway frame

    # ── Materials ─────────────────────────────────────────────────────────────
    fc: float = 4_000.0   # Specified concrete compressive strength, psi
    fy: float = 60_000.0  # Longitudinal steel yield strength, psi
    fyt: float = 60_000.0  # Transverse steel yield strength, psi  (≤ 100 ksi)

    # ── Factored loads ────────────────────────────────────────────────────────
    Pu: float = 400_000.0  # Factored axial load, lb
    Mux: float = 0.0       # Factored moment about x-axis, lb-in
    Muy: float = 0.0       # Factored moment about y-axis (biaxial), lb-in
    Vu: float = 0.0        # Factored shear force, lb

    # ── Longitudinal steel ────────────────────────────────────────────────────
    bar_size: int = 8   # Main bar number
    num_bars: int = 8   # Total number of main bars
    cover: float = 1.5  # Clear cover to ties / spiral wire, in

    # ── Transverse steel ──────────────────────────────────────────────────────
    tie_bar_size: int = 3  # Tie or spiral bar number

    # ── Sustained-load ratio ──────────────────────────────────────────────────
    beta_dns: float = 0.6  # Dead-load / total-load ratio (for EI stiffness)


@dataclass
class ColumnResults:
    """All computed results for a single column design case."""

    label: str = ""

    # ── Section ───────────────────────────────────────────────────────────────
    Ag: float = 0.0
    Ast: float = 0.0
    rho_g: float = 0.0

    # ── Axial capacity ────────────────────────────────────────────────────────
    Po: float = 0.0        # Maximum nominal capacity at zero eccentricity, lb
    Pn_max: float = 0.0    # Nominal capacity with accidental-eccentricity limit
    phi: float = 0.0       # Controlling strength-reduction factor
    phi_Pn: float = 0.0    # Design axial capacity, lb

    # ── Slenderness ───────────────────────────────────────────────────────────
    r: float = 0.0         # Radius of gyration, in
    kLu_r: float = 0.0     # Slenderness ratio
    slender: bool = False
    Cm: float = 1.0
    Pc: float = 0.0        # Euler buckling load, lb
    delta_ns: float = 1.0  # Moment-magnification factor
    Mc: float = 0.0        # Magnified design moment, lb-in

    # ── Moment capacity ───────────────────────────────────────────────────────
    phi_Mn: float = 0.0    # Design moment capacity at given Pu, lb-in

    # ── Lateral reinforcement ─────────────────────────────────────────────────
    tie_spacing: float = 0.0   # Max allowable tie spacing, in
    spiral_pitch: float = 0.0  # Required spiral pitch, in
    rho_s_min: float = 0.0     # Min spiral volumetric ratio

    # ── Utilisation ratios ────────────────────────────────────────────────────
    axial_DCR: float = 0.0
    flexure_DCR: float = 0.0

    # ── Interaction diagram ───────────────────────────────────────────────────
    interaction_points: List[Tuple[float, float]] = field(default_factory=list)

    # ── Checks ────────────────────────────────────────────────────────────────
    rho_ok: bool = True
    min_bars_ok: bool = True
    axial_ok: bool = True
    flexure_ok: bool = True
    slenderness_ok: bool = True

    # ── Diagnostics ───────────────────────────────────────────────────────────
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    status: str = "PASS"  # "PASS" | "WARN" | "FAIL"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def beta1(fc: float) -> float:
    """Depth-of-stress-block factor β₁ per ACI 318-19 Table 22.2.2.4.3."""
    if fc <= 4_000:
        return 0.85
    if fc >= 8_000:
        return 0.65
    return 0.85 - 0.05 * (fc - 4_000) / 1_000


def gross_area(inp: ColumnInput) -> float:
    """Gross cross-sectional area, in²."""
    if inp.column_type.lower() == "circular":
        return math.pi * inp.b ** 2 / 4.0
    return inp.b * inp.h


def steel_area(inp: ColumnInput) -> float:
    """Total longitudinal steel area, in²."""
    _, Ab = REBAR_DB[inp.bar_size]
    return inp.num_bars * Ab


def radius_of_gyration(inp: ColumnInput) -> float:
    """
    Approximate radius of gyration per ACI 318-19 Section 10.10.1.2.

    r = 0.30·h  for rectangular sections (about axis of bending)
    r = 0.25·D  for circular sections
    """
    if inp.column_type.lower() == "circular":
        return 0.25 * inp.b
    return 0.30 * min(inp.b, inp.h)


def Ec_concrete(fc: float, wc: float = 145.0) -> float:
    """
    Modulus of elasticity of concrete, psi.
    ACI 318-19 Section 19.2.2.1: Ec = 33·wc^1.5·√f'c
    (Normal-weight: wc = 145 pcf → Ec ≈ 57000·√f'c)
    """
    return 33.0 * (wc ** 1.5) * math.sqrt(fc)


def Ig_gross(inp: ColumnInput) -> float:
    """
    Gross moment of inertia about the axis of bending, in⁴.

    For rectangular sections the weak-axis value (b_max · b_min³ / 12) is
    used because it produces the lowest EI and therefore the lowest critical
    buckling load Pc, which gives the most conservative (largest) moment-
    magnification factor δns.
    """
    if inp.column_type.lower() == "circular":
        return math.pi * inp.b ** 4 / 64.0
    # Weak-axis Ig for conservatism in slenderness / magnification calculations
    b_max = max(inp.b, inp.h)   # longer dimension
    b_min = min(inp.b, inp.h)   # shorter dimension (bending about weak axis)
    return b_max * b_min ** 3 / 12.0


def _bar_placement(inp: ColumnInput) -> Tuple[float, float, float, float]:
    """
    Return d', d, As_comp, As_tens for simplified two-face bar layout.

    d'    = distance from compression edge to compression steel centroid, in
    d     = effective depth from compression edge to tension steel centroid, in
    As1   = compression-side steel area, in²
    As2   = tension-side steel area, in²
    """
    db_tie, _ = REBAR_DB[inp.tie_bar_size]
    db_main, Ab = REBAR_DB[inp.bar_size]
    d_prime = inp.cover + db_tie + db_main / 2.0
    if inp.column_type.lower() == "circular":
        h = inp.b
    else:
        h = inp.h
    d = h - d_prime
    # Half the bars on each face (simplified two-face model)
    n = max(2, inp.num_bars // 2)
    As1 = n * Ab
    As2 = n * Ab
    return d_prime, d, As1, As2


# =============================================================================
# P-M INTERACTION DIAGRAM
# =============================================================================


def _phi_factor(epsilon_t: float, column_type: str) -> float:
    """
    Strength-reduction factor φ interpolated from strain per
    ACI 318-19 Table 21.2.2.
    """
    phi_cc = PHI_SPIRAL if column_type.lower() == "circular" else PHI_TIED
    if epsilon_t >= EPSILON_TT:
        return PHI_TENSION
    if epsilon_t <= EPSILON_TY:
        return phi_cc
    return phi_cc + (PHI_TENSION - phi_cc) * (epsilon_t - EPSILON_TY) / (
        EPSILON_TT - EPSILON_TY
    )


def interaction_diagram(
    inp: ColumnInput, Ag: float, Ast: float, n_pts: int = 60
) -> List[Tuple[float, float]]:
    """
    Build the design P-M interaction envelope (φPn, φMn) in (lb, lb·in).

    Uses the equivalent rectangular stress block sweeping the neutral-axis
    depth from full compression to near zero.  The circular-section concrete
    compression resultant is integrated numerically.
    """
    fc_ = inp.fc
    fy_ = inp.fy
    b1 = beta1(fc_)
    d_prime, d, As1, As2 = _bar_placement(inp)
    circ = inp.column_type.lower() == "circular"
    h = inp.b if circ else inp.h
    b = inp.b  # width (rect) or diameter (circ)

    # Maximum nominal axial capacity Po  (Eq. 22.4.2.2)
    Po = 0.85 * fc_ * (Ag - Ast) + fy_ * Ast
    phi_cc = PHI_SPIRAL if circ else PHI_TIED
    Pn_max_coeff = 0.85 if circ else 0.80   # Accidental-eccentricity factor

    points: List[Tuple[float, float]] = []

    # --- Point A: pure compression -------------------------------------------
    phi_Pn_0 = phi_cc * Pn_max_coeff * Po
    points.append((phi_Pn_0, 0.0))

    # --- Sweep c from ~h down to near 0 (compression → tension) -------------
    c_start = h * 1.5         # deep neutral axis → near pure compression
    c_end = d_prime * 0.05    # very shallow → near pure tension
    c_values = [
        c_start + (c_end - c_start) * i / (n_pts - 1) for i in range(n_pts)
    ]

    for c in c_values:
        a = min(b1 * c, h)

        # ── Concrete compression resultant ────────────────────────────────
        if circ:
            # Integrate circular segment
            R = b / 2.0
            y_na = R - c          # y measured from centre, positive up
            y_top = R             # top fibre
            y_bot_block = y_top - a   # bottom of stress block
            # Area of circular segment above y_bot_block
            if y_bot_block >= R:
                Ac = 0.0
                yc = 0.0
            elif y_bot_block <= -R:
                Ac = math.pi * R ** 2
                yc = 0.0
            else:
                theta = 2.0 * math.acos(max(-1.0, min(1.0, y_bot_block / R)))
                Ac = R ** 2 * (theta - math.sin(theta)) / 2.0
                # Centroid of the circular cap above y_bot_block, measured
                # from the circle centre using the standard formula:
                #   ȳ_cap = (4R sin³(θ/2)) / (3(θ − sin θ))
                # where θ is the central angle.  The formula gives the distance
                # from the chord to the centroid of the cap, so it is added to
                # y_bot_block to obtain the y-coordinate from the circle centre.
                # This approximation places the centroid above y_bot_block,
                # slightly over-estimating the lever arm when y_bot_block < 0
                # (stress block crosses the neutral axis), which is conservative
                # for moment capacity calculations.
                if theta > 1e-9 and (theta - math.sin(theta)) > 1e-12:
                    cap_to_chord = (4.0 * R * math.sin(theta / 2.0) ** 3) / (
                        3.0 * (theta - math.sin(theta))
                    )
                    yc = y_bot_block + cap_to_chord
                else:
                    yc = y_bot_block
            Cc = 0.85 * fc_ * Ac
            # Lever arm from section centroid (at R from top):
            arm_Cc = R - yc   # dist of Cc from centroid
        else:
            Ac = a * b
            Cc = 0.85 * fc_ * Ac
            arm_Cc = h / 2.0 - a / 2.0   # from section centroid

        # ── Steel strains & stresses ──────────────────────────────────────
        eps1 = EPSILON_CU * (c - d_prime) / c    # compression steel
        eps2 = EPSILON_CU * (d - c) / c          # tension steel

        fs1 = max(min(eps1 * ES, fy_), -fy_)
        fs2 = max(min(eps2 * ES, fy_), -fy_)

        # Subtract concrete contribution at comp-steel location
        Cs = As1 * (fs1 - 0.85 * fc_)
        Ts = As2 * fs2

        arm_s1 = h / 2.0 - d_prime   # from centroid
        arm_s2 = d - h / 2.0         # from centroid

        # ── Nominal capacities ────────────────────────────────────────────
        Pn = Cc + Cs - Ts
        Mn = abs(Cc * arm_Cc + Cs * arm_s1 + As2 * fs2 * arm_s2)

        # Enforce accidental-eccentricity limit
        Pn = min(Pn, Pn_max_coeff * Po)

        # φ factor based on tensile strain
        epsilon_t = eps2
        phi = _phi_factor(epsilon_t, inp.column_type)

        points.append((phi * Pn, phi * Mn))

    # --- Point B: pure tension -----------------------------------------------
    phi_Pn_t = PHI_TENSION * (-fy_ * Ast)
    points.append((phi_Pn_t, 0.0))

    # Remove non-physical points (Pn < pure tension or Mn < 0)
    P_min = PHI_TENSION * (-fy_ * Ast)
    points = [(P, M) for P, M in points if P >= P_min and M >= 0]

    return points


def find_phi_Mn_at_Pu(
    points: List[Tuple[float, float]], Pu: float
) -> float:
    """
    Return design moment capacity φMn for a given factored axial load Pu
    by linear interpolation along the interaction envelope.
    """
    if not points:
        return 0.0

    # Sort descending by axial load
    pts = sorted(points, key=lambda p: p[0], reverse=True)

    for i in range(len(pts) - 1):
        P1, M1 = pts[i]
        P2, M2 = pts[i + 1]
        if P2 <= Pu <= P1:
            if abs(P1 - P2) < 1e-6:
                return max(M1, M2)
            t = (Pu - P1) / (P2 - P1)
            return M1 + t * (M2 - M1)

    # Below lowest or above highest — return boundary values
    if Pu > pts[0][0]:
        return pts[0][1]
    return pts[-1][1]


# =============================================================================
# SLENDERNESS
# =============================================================================


def check_slenderness(
    inp: ColumnInput,
) -> Tuple[bool, float, int]:
    """
    Determine whether the column is slender per ACI 318-19 Section 10.10.1.

    Returns (is_slender, kLu/r, slenderness_limit).
    """
    r = radius_of_gyration(inp)
    kLu_r = inp.k * inp.Lu / r

    # Non-sway limit: 34 − 12·(M1/M2) (max 40)
    # Sway limit: 22
    # Conservative assumption: M1/M2 = 0.5 → non-sway limit = 40
    limit = 40 if inp.braced else 22
    return (kLu_r > limit), kLu_r, limit


def moment_magnification(
    inp: ColumnInput, Ag: float, Ast: float, Cm: float = 1.0
) -> Tuple[float, float]:
    """
    Non-sway moment-magnification factor δns per ACI 318-19 Section 6.6.4.5.

    δns = Cm / (1 − Pu / (0.75·Pc))  ≥ 1.0

    EI per ACI 318-19 Eq. 6.6.4.4.4a:
        EI = (0.4·Ec·Ig) / (1 + βdns)

    Returns (delta_ns, Pc).
    """
    Ec = Ec_concrete(inp.fc)
    Ig = Ig_gross(inp)
    EI = (0.4 * Ec * Ig) / (1.0 + inp.beta_dns)
    Pc = math.pi ** 2 * EI / (inp.k * inp.Lu) ** 2

    denom = 1.0 - inp.Pu / (0.75 * Pc)
    if denom <= 0:
        return float("inf"), Pc   # Stability failure

    delta_ns = Cm / denom
    return max(1.0, delta_ns), Pc


# =============================================================================
# LATERAL REINFORCEMENT
# =============================================================================


def design_ties(inp: ColumnInput) -> Tuple[float, float, float, float]:
    """
    Maximum allowable tie spacing per ACI 318-19 Section 25.7.2.1:
      s ≤ min(16·db_main,  48·db_tie,  least column dimension)

    Returns (s_max, s1, s2, s3).
    """
    db_main, _ = REBAR_DB[inp.bar_size]
    db_tie, _ = REBAR_DB[inp.tie_bar_size]

    s1 = 16.0 * db_main
    s2 = 48.0 * db_tie
    s3 = inp.b if inp.column_type.lower() == "circular" else min(inp.b, inp.h)
    return min(s1, s2, s3), s1, s2, s3


def design_spiral(
    inp: ColumnInput, Ag: float
) -> Tuple[float, float, float, float]:
    """
    Design spiral reinforcement per ACI 318-19 Section 25.7.3.

    Minimum volumetric ratio:
        ρs,min = 0.45·(Ag/Ach − 1)·(f'c / fyt)   [Eq. 25.7.3.3]

    Clear spacing limits: 1 in ≤ clear ≤ 3 in  [Section 25.7.3.1]

    Returns (pitch, rho_s_min, pitch_min, pitch_max).
    """
    db_sp, As_sp = REBAR_DB[inp.tie_bar_size]
    fyt = min(inp.fyt, 100_000.0)   # ACI 318-19 Section 25.7.3.4

    # Core diameter to outside of spiral wire
    Dc = inp.b - 2.0 * inp.cover
    Ach = math.pi * Dc ** 2 / 4.0

    rho_s_min = 0.45 * (Ag / Ach - 1.0) * (inp.fc / fyt)
    rho_s_min = max(rho_s_min, 0.0)

    # Pitch from volumetric ratio: ρs = 4·As_sp / (Dc · s)
    if rho_s_min > 0:
        s_req = 4.0 * As_sp / (rho_s_min * Dc)
    else:
        s_req = 3.0 + db_sp   # default to max clear 3"

    pitch_max = 3.0 + db_sp   # 3-in clear + bar dia
    pitch_min = 1.0 + db_sp   # 1-in clear + bar dia
    pitch = min(s_req, pitch_max)
    pitch = max(pitch, pitch_min)

    return pitch, rho_s_min, pitch_min, pitch_max


# =============================================================================
# MAIN DESIGN FUNCTION
# =============================================================================


def design_column(inp: ColumnInput) -> ColumnResults:
    """
    Perform complete ACI 318-19 column design / check.

    Steps
    -----
    1.  Gross-section and steel properties
    2.  Reinforcement-ratio check
    3.  Minimum-bar check
    4.  Pure-compression capacity  (Po, Pn_max, φPn)
    5.  Slenderness check
    6.  Moment magnification (if slender, non-sway)
    7.  P-M interaction diagram → φMn at Pu
    8.  Lateral-reinforcement design (ties or spiral)
    9.  Summarise status
    """
    res = ColumnResults(label=inp.label)

    # ── 1. Section properties ─────────────────────────────────────────────────
    Ag = gross_area(inp)
    Ast = steel_area(inp)
    rho_g = Ast / Ag
    res.Ag, res.Ast, res.rho_g = Ag, Ast, rho_g

    # ── 2. Reinforcement-ratio check ──────────────────────────────────────────
    if rho_g < RHO_MIN:
        res.warnings.append(
            f"ρg = {rho_g:.4f} < ρ_min = {RHO_MIN:.2f}  (ACI 318-19 §10.6.1.1)"
        )
        res.rho_ok = False
    elif rho_g > RHO_MAX:
        res.errors.append(
            f"ρg = {rho_g:.4f} > ρ_max = {RHO_MAX:.2f}  (ACI 318-19 §10.6.1.1)"
        )
        res.rho_ok = False

    # ── 3. Minimum-bar check ──────────────────────────────────────────────────
    min_bars = 6 if inp.column_type.lower() == "circular" else 4
    if inp.num_bars < min_bars:
        res.errors.append(
            f"Number of bars ({inp.num_bars}) < minimum ({min_bars}) "
            f"(ACI 318-19 §10.7.3.1)"
        )
        res.min_bars_ok = False

    # ── 4. Axial capacity ─────────────────────────────────────────────────────
    Po = 0.85 * inp.fc * (Ag - Ast) + inp.fy * Ast   # Eq. 22.4.2.2
    circ = inp.column_type.lower() == "circular"
    phi_cc = PHI_SPIRAL if circ else PHI_TIED
    coeff = 0.85 if circ else 0.80                    # §22.4.2.1

    Pn_max = coeff * Po
    phi_Pn = phi_cc * Pn_max

    res.Po, res.Pn_max, res.phi, res.phi_Pn = Po, Pn_max, phi_cc, phi_Pn
    res.axial_DCR = inp.Pu / phi_Pn if phi_Pn > 0 else float("inf")
    res.axial_ok = inp.Pu <= phi_Pn

    # ── 5. Slenderness ────────────────────────────────────────────────────────
    r = radius_of_gyration(inp)
    res.r = r
    is_slender, kLu_r, limit = check_slenderness(inp)
    res.kLu_r, res.slender = kLu_r, is_slender

    # ── 6. Moment magnification ───────────────────────────────────────────────
    Mu = math.hypot(inp.Mux, inp.Muy) if inp.Muy else inp.Mux
    res.Cm = 1.0   # Conservative (transverse loads or unknown M1/M2)

    if is_slender and inp.braced:
        delta_ns, Pc = moment_magnification(inp, Ag, Ast, Cm=res.Cm)
        res.delta_ns, res.Pc = delta_ns, Pc
        if delta_ns == float("inf"):
            res.errors.append(
                "Column is unstable — Pu ≥ 0.75·Pc  (ACI 318-19 §6.6.4.5.2)"
            )
            res.slenderness_ok = False
        elif delta_ns > 2.5:
            res.warnings.append(
                f"δns = {delta_ns:.2f} > 2.5 — increase column size "
                f"(ACI 318-19 §6.6.4.5.2)"
            )
        Mu = delta_ns * Mu
    elif is_slender and not inp.braced:
        res.warnings.append(
            "Sway (unbraced) frame: second-order analysis required "
            "(ACI 318-19 §6.6.4.6). Moment magnification not applied."
        )

    res.Mc = Mu

    # ── 7. Interaction diagram & moment capacity ──────────────────────────────
    pts = interaction_diagram(inp, Ag, Ast)
    res.interaction_points = pts

    phi_Mn = find_phi_Mn_at_Pu(pts, inp.Pu)
    res.phi_Mn = phi_Mn
    res.flexure_DCR = Mu / phi_Mn if phi_Mn > 0 else (0.0 if Mu == 0 else float("inf"))
    res.flexure_ok = Mu <= phi_Mn if phi_Mn > 0 else (Mu == 0)

    # ── 8. Lateral reinforcement ──────────────────────────────────────────────
    if circ:
        pitch, rho_s_min, p_min, p_max = design_spiral(inp, Ag)
        res.spiral_pitch = pitch
        res.rho_s_min = rho_s_min
    else:
        s_max, _, _, _ = design_ties(inp)
        res.tie_spacing = s_max

    # ── 9. Overall status ─────────────────────────────────────────────────────
    all_ok = (
        res.rho_ok
        and res.min_bars_ok
        and res.axial_ok
        and res.flexure_ok
        and res.slenderness_ok
    )
    if res.errors or not all_ok:
        res.status = "FAIL"
    elif res.warnings:
        res.status = "WARN"
    else:
        res.status = "PASS"

    return res


# =============================================================================
# CONSOLE REPORT
# =============================================================================


def print_report(inp: ColumnInput, res: ColumnResults) -> None:
    """Print a formatted design-check report to stdout."""
    W = 70
    bar = "=" * W
    print(bar)
    print(f"  ACI 318-19 RC Column Design Report — {res.label}".center(W))
    print(bar)

    def row(key: str, val: str) -> None:
        print(f"  {key:<38} {val}")

    print("\n  ── GEOMETRY & MATERIALS ──────────────────────────────────────")
    if inp.column_type.lower() == "circular":
        row("Section:", f"Circular  D = {inp.b:.2f} in")
    else:
        row("Section:", f"Rectangular  b × h = {inp.b:.2f} × {inp.h:.2f} in")
    row("Clear height Lu:", f"{inp.Lu:.2f} in ({inp.Lu/12:.2f} ft)")
    row("Effective length factor k:", f"{inp.k:.2f}")
    row("Frame type:", "Braced (non-sway)" if inp.braced else "Unbraced (sway)")
    row("f'c:", f"{inp.fc:,.0f} psi  ({inp.fc/1000:.1f} ksi)")
    row("fy:", f"{inp.fy:,.0f} psi  ({inp.fy/1000:.1f} ksi)")
    row("fyt (transverse):", f"{inp.fyt:,.0f} psi  ({inp.fyt/1000:.1f} ksi)")

    print("\n  ── SECTION PROPERTIES ────────────────────────────────────────")
    row("Gross area Ag:", f"{res.Ag:.2f} in²")
    row("Main bars:", f"{inp.num_bars} — #{inp.bar_size}  (As = {res.Ast:.2f} in²)")
    row("ρg = Ast / Ag:", f"{res.rho_g:.4f}  [{RHO_MIN:.2f} – {RHO_MAX:.2f}]  {'✓' if res.rho_ok else '✗'}")

    print("\n  ── FACTORED LOADS ────────────────────────────────────────────")
    row("Pu:", f"{inp.Pu:,.0f} lb  ({inp.Pu/1000:.1f} kips)")
    row("Mux:", f"{inp.Mux:,.0f} lb·in  ({inp.Mux/12000:.2f} kip·ft)")
    if inp.Muy:
        row("Muy:", f"{inp.Muy:,.0f} lb·in  ({inp.Muy/12000:.2f} kip·ft)")

    print("\n  ── AXIAL CAPACITY ────────────────────────────────────────────")
    row("Po (zero eccentricity):", f"{res.Po/1000:.1f} kips")
    row("Pn,max (accidental ecc.):", f"{res.Pn_max/1000:.1f} kips")
    row(f"φ = {res.phi:.2f}  →  φPn:", f"{res.phi_Pn/1000:.1f} kips")
    row("Demand/Capacity  Pu / φPn:", f"{res.axial_DCR:.3f}  {'✓' if res.axial_ok else '✗'}")

    print("\n  ── SLENDERNESS ───────────────────────────────────────────────")
    row("Radius of gyration r:", f"{res.r:.3f} in")
    row("kLu / r:", f"{res.kLu_r:.1f}")
    row("Column classification:", "SLENDER" if res.slender else "SHORT (non-slender)")
    if res.slender and inp.braced:
        row("Pc (Euler buckling load):", f"{res.Pc/1000:.1f} kips")
        row("δns (magnification factor):", f"{res.delta_ns:.3f}")
    row("Magnified moment Mc:", f"{res.Mc/12000:.2f} kip·ft")

    print("\n  ── MOMENT CAPACITY ───────────────────────────────────────────")
    row("φMn at given Pu:", f"{res.phi_Mn/12000:.2f} kip·ft")
    row("Mc / φMn:", f"{res.flexure_DCR:.3f}  {'✓' if res.flexure_ok else '✗'}")

    print("\n  ── LATERAL REINFORCEMENT ─────────────────────────────────────")
    if inp.column_type.lower() == "circular":
        row(f"#{inp.tie_bar_size} Spiral — ρs,min:", f"{res.rho_s_min:.4f}")
        row("Spiral pitch:", f"{res.spiral_pitch:.2f} in")
    else:
        row(f"#{inp.tie_bar_size} Ties — max spacing:", f"{res.tie_spacing:.2f} in")

    print("\n  ── STATUS ────────────────────────────────────────────────────")
    if res.warnings:
        for w in res.warnings:
            print(f"  ⚠  {w}")
    if res.errors:
        for e in res.errors:
            print(f"  ✗  {e}")

    status_sym = {"PASS": "✓  PASS", "WARN": "⚠  PASS WITH WARNINGS", "FAIL": "✗  FAIL"}
    print(f"\n  Overall: {status_sym.get(res.status, res.status)}")
    print(bar + "\n")


# =============================================================================
# EXCEL OUTPUT
# =============================================================================

# ── Style helpers ─────────────────────────────────────────────────────────────

_BLUE_DARK = "1F3864"
_BLUE_MID = "2E75B6"
_BLUE_LIGHT = "BDD7EE"
_GREEN = "E2EFDA"
_RED = "FCE4D6"
_YELLOW = "FFF2CC"
_WHITE = "FFFFFF"
_GREY = "F2F2F2"


def _font(bold: bool = False, size: int = 10, color: str = "000000") -> Font:
    return Font(name="Calibri", bold=bold, size=size, color=color)


def _fill(hex_color: str) -> PatternFill:
    return PatternFill("solid", fgColor=hex_color)


def _thin_border() -> Border:
    s = Side(border_style="thin", color="A0A0A0")
    return Border(left=s, right=s, top=s, bottom=s)


def _center() -> Alignment:
    return Alignment(horizontal="center", vertical="center", wrap_text=True)


def _left() -> Alignment:
    return Alignment(horizontal="left", vertical="center", wrap_text=True)


def _set_cell(
    ws,
    row: int,
    col: int,
    value=None,
    bold: bool = False,
    size: int = 10,
    fc: str = _WHITE,
    color: str = "000000",
    align: str = "left",
    border: bool = True,
    number_format: str = "General",
) -> None:
    cell = ws.cell(row=row, column=col, value=value)
    cell.font = _font(bold=bold, size=size, color=color)
    cell.fill = _fill(fc)
    if border:
        cell.border = _thin_border()
    cell.alignment = _center() if align == "center" else _left()
    cell.number_format = number_format


def _header_row(ws, row: int, cols: int, title: str, start_col: int = 1) -> None:
    """Merge cells and write a section header."""
    ws.merge_cells(
        start_row=row, start_column=start_col,
        end_row=row, end_column=start_col + cols - 1,
    )
    cell = ws.cell(row=row, column=start_col, value=title)
    cell.font = _font(bold=True, size=11, color=_WHITE)
    cell.fill = _fill(_BLUE_MID)
    cell.alignment = _center()
    cell.border = _thin_border()


def _status_color(status: str) -> str:
    return {"PASS": _GREEN, "WARN": _YELLOW, "FAIL": _RED}.get(status, _WHITE)


# ── Input sheet ───────────────────────────────────────────────────────────────

def _build_input_sheet(wb: "Workbook", cases: List[ColumnInput]) -> None:
    """
    Create the 'Input' sheet with parameter tables for every design case.

    Cases are laid out in two-column pairs (each pair shares the same row
    band).  Any number of cases is supported: pairs are stacked vertically
    with a blank separator row between them.
    """
    ws = wb.create_sheet("Input")
    ws.sheet_view.showGridLines = False

    # Title
    ws.merge_cells("A1:G1")
    c = ws["A1"]
    c.value = "RC Column Design — ACI 318-19  |  Input Parameters"
    c.font = _font(bold=True, size=14, color=_WHITE)
    c.fill = _fill(_BLUE_DARK)
    c.alignment = _center()
    c.border = _thin_border()
    ws.row_dimensions[1].height = 30

    ws.merge_cells("A2:G2")
    c = ws["A2"]
    c.value = (
        "All forces in lb and lb·in (or kips / kip·ft)  |  "
        "All dimensions in inches  |  "
        "Stresses in psi"
    )
    c.font = _font(size=9, color="555555")
    c.fill = _fill(_GREY)
    c.alignment = _center()
    c.border = _thin_border()

    # Column widths
    widths = [22, 14, 10, 22, 14, 10, 4]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    param_blocks = [
        ("GEOMETRY", [
            ("Section type", "column_type", "rectangular / circular"),
            ("Width b  (or diameter D for circular)", "b", "in"),
            ("Depth h  (rectangular only)", "h", "in"),
            ("Unsupported length Lu", "Lu", "in"),
            ("Effective length factor k", "k", "—"),
            ("Frame type", "braced", "braced / unbraced"),
        ]),
        ("MATERIALS", [
            ("Concrete  f'c", "fc", "psi"),
            ("Long. steel  fy", "fy", "psi"),
            ("Trans. steel  fyt", "fyt", "psi"),
        ]),
        ("FACTORED LOADS", [
            ("Axial load  Pu", "Pu", "lb"),
            ("Moment about x-axis  Mux", "Mux", "lb·in"),
            ("Moment about y-axis  Muy", "Muy", "lb·in"),
            ("Shear  Vu", "Vu", "lb"),
        ]),
        ("LONGITUDINAL REINFORCEMENT", [
            ("Bar size  (#)", "bar_size", "—"),
            ("Number of bars", "num_bars", "—"),
            ("Clear cover to ties / spiral", "cover", "in"),
        ]),
        ("TRANSVERSE REINFORCEMENT", [
            ("Tie / spiral bar size  (#)", "tie_bar_size", "—"),
        ]),
        ("ADVANCED", [
            ("Sustained-load ratio  βdns", "beta_dns", "0 – 1"),
        ]),
    ]

    # Height (in rows) of one complete block set (all param_blocks stacked)
    rows_per_block_set = sum(1 + len(params) for _, params in param_blocks)
    # Separator rows between pairs
    SEPARATOR = 1

    # Layout: two cases per row-band.  Pairs are stacked downward.
    for ci, case in enumerate(cases):
        pair_index = ci // 2          # which vertical pair this case belongs to
        side = ci % 2                 # 0 = left (col 1), 1 = right (col 4)
        col_off = 1 + side * 3        # starting column: 1 or 4

        # Top row for this pair band
        band_start = 3 + pair_index * (rows_per_block_set + SEPARATOR)

        current_row = band_start
        for block_name, params in param_blocks:
            _header_row(ws, current_row, 3,
                        f"  {case.label}  —  {block_name}", start_col=col_off)
            ws.row_dimensions[current_row].height = 18
            current_row += 1

            for pname, pattr, punit in params:
                val = getattr(case, pattr)
                if isinstance(val, bool):
                    val = "Braced" if val else "Unbraced"
                _set_cell(ws, current_row, col_off, pname, fc=_GREY)
                _set_cell(ws, current_row, col_off + 1, val,
                          bold=True, fc=_BLUE_LIGHT, align="center")
                _set_cell(ws, current_row, col_off + 2, punit,
                          fc=_GREY, align="center")
                ws.row_dimensions[current_row].height = 16
                current_row += 1



def _build_results_sheet(
    wb: "Workbook",
    cases: List[ColumnInput],
    results: List[ColumnResults],
) -> None:
    """Create the 'Results' sheet with a detailed calculation table."""
    ws = wb.create_sheet("Results")
    ws.sheet_view.showGridLines = False

    # ── Title ─────────────────────────────────────────────────────────────────
    ws.merge_cells("A1:H1")
    c = ws["A1"]
    c.value = "RC Column Design — ACI 318-19  |  Summary of Results"
    c.font = _font(bold=True, size=14, color=_WHITE)
    c.fill = _fill(_BLUE_DARK)
    c.alignment = _center()
    c.border = _thin_border()
    ws.row_dimensions[1].height = 30

    # ── Column widths ─────────────────────────────────────────────────────────
    col_w = [6, 32, 14, 14, 14, 14, 14, 14]
    for i, w in enumerate(col_w, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    # ── Headers ───────────────────────────────────────────────────────────────
    hdrs = ["#", "Parameter", "Unit"] + [r.label for r in results]
    row = 2
    for ci, h in enumerate(hdrs[:3 + len(results)], 1):
        _set_cell(ws, row, ci, h, bold=True, fc=_BLUE_MID, color=_WHITE, align="center")
    ws.row_dimensions[row].height = 20
    row += 1

    def _data_rows() -> List[Tuple[str, str, List]]:
        """Return rows: (section_title, unit, [value per case])."""
        rows = []

        # ── Status ──────────────────────────────────────────────────────────
        rows.append(("STATUS", "", [r.status for r in results]))
        rows.append(("───── SECTION ─────", "", [""] * len(results)))
        rows.append(("Gross area  Ag", "in²", [f"{r.Ag:.2f}" for r in results]))
        rows.append(("Total steel  Ast", "in²", [f"{r.Ast:.3f}" for r in results]))
        rows.append(("Steel ratio  ρg = Ast/Ag", "—", [f"{r.rho_g:.4f}" for r in results]))
        rows.append(("ρg within limits [0.01, 0.08]?", "—", ["YES" if r.rho_ok else "NO" for r in results]))

        # ── Materials / beta1 ────────────────────────────────────────────────
        rows.append(("β₁ (stress-block factor)", "—", [f"{beta1(inp.fc):.3f}" for inp in cases]))
        rows.append(("Ec (concrete modulus)", "ksi", [f"{Ec_concrete(inp.fc)/1000:.0f}" for inp in cases]))

        # ── Axial capacity ───────────────────────────────────────────────────
        rows.append(("───── AXIAL CAPACITY ─────", "", [""] * len(results)))
        rows.append(("Po (zero eccentricity)", "kips", [f"{r.Po/1000:.1f}" for r in results]))
        rows.append(("Pn,max (accidental ecc.)", "kips", [f"{r.Pn_max/1000:.1f}" for r in results]))
        rows.append(("φ (strength-reduction factor)", "—", [f"{r.phi:.2f}" for r in results]))
        rows.append(("φPn (design axial capacity)", "kips", [f"{r.phi_Pn/1000:.1f}" for r in results]))
        rows.append(("Pu (factored axial load)", "kips", [f"{inp.Pu/1000:.1f}" for inp in cases]))
        rows.append(("DCR = Pu / φPn", "—", [f"{r.axial_DCR:.3f}" for r in results]))
        rows.append(("Axial capacity OK?", "—", ["YES" if r.axial_ok else "NO" for r in results]))

        # ── Slenderness ──────────────────────────────────────────────────────
        rows.append(("───── SLENDERNESS ─────", "", [""] * len(results)))
        rows.append(("Radius of gyration  r", "in", [f"{r.r:.3f}" for r in results]))
        rows.append(("kLu / r", "—", [f"{r.kLu_r:.1f}" for r in results]))
        rows.append(("Slender?", "—", ["SLENDER" if r.slender else "SHORT" for r in results]))
        rows.append(("δns (magnification factor)", "—", [f"{r.delta_ns:.3f}" for r in results]))
        rows.append(("Pc (Euler buckling load)", "kips", [f"{r.Pc/1000:.1f}" if r.Pc else "—" for r in results]))
        rows.append(("Mc (magnified moment)", "kip·ft", [f"{r.Mc/12000:.2f}" for r in results]))

        # ── Moment capacity ──────────────────────────────────────────────────
        rows.append(("───── MOMENT CAPACITY ─────", "", [""] * len(results)))
        rows.append(("φMn at given Pu", "kip·ft", [f"{r.phi_Mn/12000:.2f}" for r in results]))
        rows.append(("Mc / φMn  (flexure DCR)", "—", [f"{r.flexure_DCR:.3f}" for r in results]))
        rows.append(("Moment capacity OK?", "—", ["YES" if r.flexure_ok else "NO" for r in results]))

        # ── Lateral reinforcement ─────────────────────────────────────────────
        rows.append(("───── LATERAL REINFORCEMENT ─────", "", [""] * len(results)))
        rows.append(("Tie max spacing", "in",
                     [f"{r.tie_spacing:.2f}" if r.tie_spacing else "—" for r in results]))
        rows.append(("Spiral pitch", "in",
                     [f"{r.spiral_pitch:.2f}" if r.spiral_pitch else "—" for r in results]))
        rows.append(("Spiral ρs,min", "—",
                     [f"{r.rho_s_min:.4f}" if r.rho_s_min else "—" for r in results]))

        return rows

    # Pre-compute the data rows once to avoid repeated calls inside the loop.
    all_rows = _data_rows()
    # Pre-count how many section-header rows precede each position (for
    # computing the 1-based data-row number shown in the first column).
    section_counts: List[int] = []
    running = 0
    for param, _, _ in all_rows:
        if param.startswith("─"):
            running += 1
        section_counts.append(running)

    for local_i, (param, unit, vals) in enumerate(all_rows):
        ri = row + local_i
        is_section = param.startswith("─")
        is_status = param == "STATUS"
        row_bg = _GREY if is_section else _WHITE

        if is_section:
            ws.merge_cells(
                start_row=ri, start_column=1, end_row=ri, end_column=2 + len(results)
            )
            _set_cell(ws, ri, 1, param, bold=True, fc=_BLUE_DARK, color=_WHITE, align="center")
            ws.row_dimensions[ri].height = 16
            continue

        # 1-based row number (excluding section headers)
        data_row_num = local_i + 1 - section_counts[local_i]
        _set_cell(ws, ri, 1, data_row_num, fc=row_bg, align="center")

        _set_cell(ws, ri, 2, param, fc=row_bg)
        _set_cell(ws, ri, 3, unit, fc=row_bg, align="center")

        for ci, val in enumerate(vals, start=4):
            if is_status:
                bg = _status_color(val)
                _set_cell(ws, ri, ci, val, bold=True, fc=bg, align="center")
            elif param in ("Axial capacity OK?", "ρg within limits [0.01, 0.08]?",
                           "Moment capacity OK?", "Slender?"):
                ok = val in ("YES", "SHORT")
                bg = _GREEN if ok else _RED
                _set_cell(ws, ri, ci, val, bold=True, fc=bg, align="center")
            else:
                _set_cell(ws, ri, ci, val, align="center", fc=row_bg)

        ws.row_dimensions[ri].height = 16

    # Freeze top rows
    ws.freeze_panes = "A3"


def _build_interaction_sheet(
    wb: "Workbook",
    cases: List[ColumnInput],
    results: List[ColumnResults],
) -> None:
    """Create a sheet with P-M interaction data and chart for each case."""
    ws = wb.create_sheet("Interaction Diagram")
    ws.sheet_view.showGridLines = False

    # Title
    ws.merge_cells("A1:I1")
    c = ws["A1"]
    c.value = "P-M Interaction Diagrams — ACI 318-19"
    c.font = _font(bold=True, size=14, color=_WHITE)
    c.fill = _fill(_BLUE_DARK)
    c.alignment = _center()
    c.border = _thin_border()
    ws.row_dimensions[1].height = 30

    # Build data columns: [φMn (kip·ft), φPn (kips)] per case side by side
    # Leave 2 blank columns between cases
    col = 1
    chart_refs = []

    for ci, (inp, res) in enumerate(zip(cases, results)):
        pts = res.interaction_points
        # Convert to kips and kip·ft
        Mvals = [p[1] / 12_000 for p in pts]
        Pvals = [p[0] / 1_000  for p in pts]

        # Headers
        ws.column_dimensions[get_column_letter(col)].width = 14
        ws.column_dimensions[get_column_letter(col + 1)].width = 14

        ws.merge_cells(
            start_row=2, start_column=col, end_row=2, end_column=col + 1
        )
        hdr = ws.cell(row=2, column=col, value=f"{res.label}  —  Interaction")
        hdr.font = _font(bold=True, size=10, color=_WHITE)
        hdr.fill = _fill(_BLUE_MID)
        hdr.alignment = _center()
        hdr.border = _thin_border()

        _set_cell(ws, 3, col,     "φMn  (kip·ft)", bold=True, fc=_BLUE_LIGHT, align="center")
        _set_cell(ws, 3, col + 1, "φPn  (kips)",   bold=True, fc=_BLUE_LIGHT, align="center")

        M_start_row = 4
        for ri, (M, P) in enumerate(zip(Mvals, Pvals), start=M_start_row):
            _set_cell(ws, ri, col,     round(M, 2), align="center")
            _set_cell(ws, ri, col + 1, round(P, 2), align="center")

        n_data = len(Mvals)

        # Demand point
        dem_row = M_start_row + n_data + 1
        _set_cell(ws, dem_row, col,     "DEMAND POINT", bold=True, fc=_YELLOW, align="center")
        _set_cell(ws, dem_row, col + 1, "",            fc=_YELLOW, align="center")
        ws.merge_cells(
            start_row=dem_row, start_column=col, end_row=dem_row, end_column=col + 1
        )

        Mu_dem = res.Mc / 12_000
        Pu_dem = inp.Pu / 1_000
        _set_cell(ws, dem_row + 1, col,     round(Mu_dem, 2), bold=True, fc=_YELLOW, align="center")
        _set_cell(ws, dem_row + 1, col + 1, round(Pu_dem, 2), bold=True, fc=_YELLOW, align="center")

        chart_refs.append(
            (col, M_start_row, n_data, dem_row + 1, res.label)
        )

        col += 3  # gap between cases

    # ── Build scatter chart ───────────────────────────────────────────────────
    chart = ScatterChart()
    chart.title = "P-M Interaction Diagrams"
    chart.style = 10
    chart.x_axis.title = "φMn  (kip·ft)"
    chart.y_axis.title = "φPn  (kips)"
    chart.width = 18
    chart.height = 14

    colors = ["2E75B6", "C00000", "70AD47", "ED7D31"]

    for ci, (col0, m_start, n_data, dem_row, lbl) in enumerate(chart_refs):
        color = colors[ci % len(colors)]

        # Capacity curve
        x_cap = Reference(ws, min_col=col0,     min_row=m_start, max_row=m_start + n_data - 1)
        y_cap = Reference(ws, min_col=col0 + 1, min_row=m_start, max_row=m_start + n_data - 1)
        ser_cap = Series(y_cap, x_cap, title=f"{lbl} – Capacity")
        ser_cap.marker.symbol = "none"
        ser_cap.graphicalProperties.line.solidFill = color
        ser_cap.graphicalProperties.line.width = 18000  # 1.8 pt
        chart.series.append(ser_cap)

        # Demand point
        x_dem = Reference(ws, min_col=col0,     min_row=dem_row)
        y_dem = Reference(ws, min_col=col0 + 1, min_row=dem_row)
        ser_dem = Series(y_dem, x_dem, title=f"{lbl} – Demand")
        ser_dem.marker.symbol = "diamond"
        ser_dem.marker.size = 8
        ser_dem.graphicalProperties.line.noFill = True
        ser_dem.marker.graphicalProperties.solidFill = color
        ser_dem.marker.graphicalProperties.line.solidFill = color
        chart.series.append(ser_dem)

    # Place chart to the right of the data
    anchor_col = col + 1
    ws.add_chart(chart, f"{get_column_letter(anchor_col)}2")


# ── Public entry point ────────────────────────────────────────────────────────

def write_excel(
    cases: List[ColumnInput],
    results: List[ColumnResults],
    path: str = "rc_column_design.xlsx",
) -> str:
    """
    Write all design cases to an Excel workbook.

    Sheets
    ------
    Input              — user parameters
    Results            — summary table with colour-coded checks
    Interaction Diagram — P-M data table and scatter chart

    Returns the absolute path of the written file.
    """
    if not OPENPYXL_AVAILABLE:
        print("openpyxl is not installed. Run:  pip install openpyxl")
        return ""

    wb = Workbook()
    # Remove default sheet
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    _build_input_sheet(wb, cases)
    _build_results_sheet(wb, cases, results)
    _build_interaction_sheet(wb, cases, results)

    wb.save(path)
    return os.path.abspath(path)


# =============================================================================
# BUILT-IN EXAMPLE CASES
# =============================================================================


def _example_cases() -> List[ColumnInput]:
    """Return a list of representative design cases."""
    return [
        # ── Case 1: Short rectangular tied column under axial + bending ───────
        ColumnInput(
            label="C1 – Rect. Tied (Short)",
            column_type="rectangular",
            b=16.0, h=20.0,
            Lu=120.0, k=1.0, braced=True,
            fc=4_000, fy=60_000, fyt=60_000,
            Pu=450_000, Mux=1_200_000, Muy=0,
            bar_size=9, num_bars=8, cover=1.5,
            tie_bar_size=3,
            beta_dns=0.6,
        ),
        # ── Case 2: Slender rectangular column ────────────────────────────────
        ColumnInput(
            label="C2 – Rect. Tied (Slender)",
            column_type="rectangular",
            b=12.0, h=12.0,
            Lu=240.0, k=1.0, braced=True,
            fc=5_000, fy=60_000, fyt=60_000,
            Pu=180_000, Mux=600_000, Muy=0,
            bar_size=7, num_bars=6, cover=1.5,
            tie_bar_size=3,
            beta_dns=0.6,
        ),
        # ── Case 3: Circular spiral column ────────────────────────────────────
        ColumnInput(
            label="C3 – Circular Spiral",
            column_type="circular",
            b=20.0, h=20.0,
            Lu=144.0, k=0.8, braced=True,
            fc=5_000, fy=60_000, fyt=60_000,
            Pu=600_000, Mux=900_000, Muy=0,
            bar_size=8, num_bars=8, cover=1.5,
            tie_bar_size=3,
            beta_dns=0.6,
        ),
        # ── Case 4: Pure compression (gravity only) ───────────────────────────
        ColumnInput(
            label="C4 – Rect. Pure Compression",
            column_type="rectangular",
            b=18.0, h=18.0,
            Lu=144.0, k=0.65, braced=True,
            fc=6_000, fy=60_000, fyt=60_000,
            Pu=900_000, Mux=0, Muy=0,
            bar_size=10, num_bars=8, cover=1.5,
            tie_bar_size=4,
            beta_dns=0.7,
        ),
    ]


# =============================================================================
# CLI
# =============================================================================


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="ACI 318-19 Reinforced Concrete Column Design",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--output", "-o",
        default="rc_column_design.xlsx",
        help="Output Excel file path (default: rc_column_design.xlsx)",
    )
    p.add_argument(
        "--no-excel",
        action="store_true",
        help="Skip Excel output (print report only)",
    )
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)

    cases = _example_cases()
    results = [design_column(c) for c in cases]

    # Print console reports
    for inp, res in zip(cases, results):
        print_report(inp, res)

    # Write Excel
    if not args.no_excel:
        if OPENPYXL_AVAILABLE:
            out = write_excel(cases, results, path=args.output)
            print(f"✓ Excel workbook written → {out}")
        else:
            print(
                "⚠  openpyxl not installed — skipping Excel output.\n"
                "   Install with:  pip install openpyxl"
            )

    failed = sum(1 for r in results if r.status == "FAIL")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
