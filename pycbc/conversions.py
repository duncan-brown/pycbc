# Copyright (C) 2017  Collin Capano, Christopher M. Biwer
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
# Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.


#
# =============================================================================
#
#                                   Preamble
#
# =============================================================================
#
"""
This modules provides a library of functions that calculate waveform parameters
from other parameters. All exposed functions in this module's namespace return
one parameter given a set of inputs.
"""

import copy
import numpy
import lal
import lalsimulation as lalsim
from pycbc.detector import Detector

from .coordinates import spherical_to_cartesian as _spherical_to_cartesian

#
# =============================================================================
#
#                           Helper functions
#
# =============================================================================
#
def ensurearray(arg):
    """Ensures that the given argument is a numpy array. If it is not, the
    argument is converted to an array.
    """
    input_is_array = isinstance(arg, numpy.ndarray)
    if not input_is_array:
        arr = numpy.array(arg)
        arg = arr
    return arg, input_is_array


def formatreturn(arg, input_is_array=False):
    """If the given argument is a numpy array with shape (1,), just returns
    that value."""
    if not input_is_array and arg.size == 1:
        arg = arg.item()
    return arg

#
# =============================================================================
#
#                           CBC mass functions
#
# =============================================================================
#
def primary_mass(mass1, mass2):
    """Returns the larger of mass1 and mass2 (p = primary)."""
    mass1, ia1 = ensurearray(mass1)
    mass2, ia2 = ensurearray(mass2)
    input_is_array = ia1 or ia2
    if mass1.shape != mass2.shape:
        raise ValueError("mass1 and mass2 must have same shape")
    mp = copy.copy(mass1)
    mask = mass1 < mass2
    mp[mask] = mass2[mask]
    return formatreturn(mp, input_is_array)


def secondary_mass(mass1, mass2):
    """Returns the smaller of mass1 and mass2 (s = secondary)."""
    mass1, ia1 = ensurearray(mass1)
    mass2, ia2 = ensurearray(mass2)
    input_is_array = ia1 or ia2
    if mass1.shape != mass2.shape:
        raise ValueError("mass1 and mass2 must have same shape")
    ms = copy.copy(mass2)
    mask = mass1 < mass2
    ms[mask] = mass1[mask]
    return formatreturn(ms, input_is_array)


def mtotal_from_mass1_mass2(mass1, mass2):
    """Returns the total mass from mass1 and mass2."""
    return mass1 + mass2


def q_from_mass1_mass2(mass1, mass2):
    """Returns the mass ratio m1/m2, where m1 >= m2."""
    return primary_mass(mass1, mass2) / secondary_mass(mass1, mass2)


def invq_from_mass1_mass2(mass1, mass2):
    """Returns the inverse mass ratio m2/m1, where m1 >= m2."""
    return secondary_mass(mass1, mass2) / primary_mass(mass1, mass2)


def eta_from_mass1_mass2(mass1, mass2):
    """Returns the symmetric mass ratio from mass1 and mass2."""
    return mass1*mass2 / (mass1+mass2)**2.


def mchirp_from_mass1_mass2(mass1, mass2):
    """Returns the chirp mass from mass1 and mass2."""
    return eta_from_mass1_mass2(mass1, mass2)**(3./5) * (mass1+mass2)


def mass1_from_mtotal_q(mtotal, q):
    """Returns a component mass from the given total mass and mass ratio.

    If the mass ratio q is >= 1, the returned mass will be the primary
    (heavier) mass. If q < 1, the returned mass will be the secondary
    (lighter) mass.
    """
    return q*mtotal / (1.+q)


def mass2_from_mtotal_q(mtotal, q):
    """Returns a component mass from the given total mass and mass ratio.

    If the mass ratio q is >= 1, the returned mass will be the secondary
    (lighter) mass. If q < 1, the returned mass will be the primary (heavier)
    mass.
    """
    return mtotal / (1.+q)


def mass1_from_mtotal_eta(mtotal, eta):
    """Returns the primary mass from the total mass and symmetric mass
    ratio.
    """
    return 0.5 * mtotal * (1.0 + (1.0 - 4.0 * eta)**0.5)


def mass2_from_mtotal_eta(mtotal, eta):
    """Returns the secondary mass from the total mass and symmetric mass
    ratio.
    """
    return 0.5 * mtotal * (1.0 - (1.0 - 4.0 * eta)**0.5)


def mtotal_from_mchirp_eta(mchirp, eta):
    """Returns the total mass from the chirp mass and symmetric mass ratio.
    """
    return mchirp / (eta**(3./5.))


def mass1_from_mchirp_eta(mchirp, eta):
    """Returns the primary mass from the chirp mass and symmetric mass ratio.
    """
    mtotal = mtotal_from_mchirp_eta(mchirp, eta)
    return mass1_from_mtotal_eta(mtotal, eta)


def mass2_from_mchirp_eta(mchirp, eta):
    """Returns the primary mass from the chirp mass and symmetric mass ratio.
    """
    mtotal = mtotal_from_mchirp_eta(mchirp, eta)
    return mass2_from_mtotal_eta(mtotal, eta)


def _mass2_from_mchirp_mass1(mchirp, mass1):
    r"""Returns the secondary mass from the chirp mass and primary mass.

    As this is a cubic equation this requires finding the roots and returning
    the one that is real. Basically it can be shown that:

    .. math::
        m_2^3 - a(m_2 + m_1) = 0,

    where

    .. math::
        a = \frac{\mathcal{M}^5}{m_1^3}.

    This has 3 solutions but only one will be real.
    """
    a = mchirp**5 / mass1**3
    roots = numpy.roots([1,0,-a,-a*mass1])
    # Find the real one
    real_root = roots[(abs(roots - roots.real)).argmin()]
    return real_root.real

mass2_from_mchirp_mass1 = numpy.vectorize(_mass2_from_mchirp_mass1)


def _mass_from_knownmass_eta(known_mass, eta, known_is_secondary=False,
                            force_real=True):
    r"""Returns the other component mass given one of the component masses
    and the symmetric mass ratio.

    This requires finding the roots of the quadratic equation:

    .. math::
        \eta m_2^2 + (2\eta - 1)m_1 m_2 + \eta m_1^2 = 0.

    This has two solutions which correspond to :math:`m_1` being the heavier
    mass or it being the lighter mass. By default, `known_mass` is assumed to
    be the heavier (primary) mass, and the smaller solution is returned. Use
    the `other_is_secondary` to invert.

    Parameters
    ----------
    known_mass : float
        The known component mass.
    eta : float
        The symmetric mass ratio.
    known_is_secondary : {False, bool}
        Whether the known component mass is the primary or the secondary. If
        True, `known_mass` is assumed to be the secondary (lighter) mass and
        the larger solution is returned. Otherwise, the smaller solution is
        returned. Default is False.
    force_real : {True, bool}
        Force the returned mass to be real.

    Returns
    -------
    float
        The other component mass.
    """
    roots = numpy.roots([eta, (2*eta - 1)*known_mass, eta*known_mass**2.])
    if force_real:
        roots = numpy.real(roots)
    if known_is_secondary:
        return roots[roots.argmax()]
    else:
        return roots[roots.argmin()]

mass_from_knownmass_eta = numpy.vectorize(_mass_from_knownmass_eta)


def mass2_from_mass1_eta(mass1, eta, force_real=True):
    """Returns the secondary mass from the primary mass and symmetric mass
    ratio.
    """
    return mass_from_knownmass_eta(mass1, eta, known_is_secondary=False,
                                   force_real=force_real)


def mass1_from_mass2_eta(mass2, eta, force_real=True):
    """Returns the primary mass from the secondary mass and symmetric mass
    ratio.
    """
    return mass_from_knownmass_eta(mass2, eta, known_is_secondary=True,
                                   force_real=force_real)


def eta_from_q(q):
    r"""Returns the symmetric mass ratio from the given mass ratio.

    This is given by:

    .. math::
        \eta = \frac{q}{(1+q)^2}.

    Note that the mass ratio may be either < 1 or > 1.
    """
    return q / (1.+q)**2


def mass1_from_mchirp_q(mchirp, q):
    """Returns the primary mass from the given chirp mass and mass ratio."""
    mass1 = (q**(2./5.))*((1.0 + q)**(1./5.))*mchirp
    return mass1

def mass2_from_mchirp_q(mchirp, q):
    """Returns the secondary mass from the given chirp mass and mass ratio."""
    mass2 = (q**(-3./5.))*((1.0 + q)**(1./5.))*mchirp
    return mass2

def _a0(f_lower):
    """Used in calculating chirp times: see Cokelaer, arxiv.org:0706.4437
       appendix 1, also lalinspiral/python/sbank/tau0tau3.py.
    """
    return 5. / (256. * (numpy.pi * f_lower)**(8./3.))

def _a3(f_lower):
    """Another parameter used for chirp times"""
    return numpy.pi / (8. * (numpy.pi * f_lower)**(5./3.))


def tau0_from_mtotal_eta(mtotal, eta, f_lower):
    r"""Returns :math:`\tau_0` from the total mass, symmetric mass ratio, and
    the given frequency.
    """
    # convert to seconds
    mtotal = mtotal * lal.MTSUN_SI
    # formulae from arxiv.org:0706.4437
    return _a0(f_lower) / (mtotal**(5./3.) * eta)


def tau3_from_mtotal_eta(mtotal, eta, f_lower):
    r"""Returns :math:`\tau_0` from the total mass, symmetric mass ratio, and
    the given frequency.
    """
    # convert to seconds
    mtotal = mtotal * lal.MTSUN_SI
    # formulae from arxiv.org:0706.4437
    return _a3(f_lower) / (mtotal**(2./3.) * eta)


def tau0_from_mass1_mass2(mass1, mass2, f_lower):
    r"""Returns :math:`\tau_0` from the component masses and given frequency.
    """
    mtotal = mass1 + mass2
    eta = eta_from_mass1_mass2(mass1, mass2)
    return tau0_from_mtotal_eta(mtotal, eta, f_lower)


def tau3_from_mass1_mass2(mass1, mass2, f_lower):
    r"""Returns :math:`\tau_3` from the component masses and given frequency.
    """
    mtotal = mass1 + mass2
    eta = eta_from_mass1_mass2(mass1, mass2)
    return tau3_from_mtotal_eta(mtotal, eta, f_lower)


def mtotal_from_tau0_tau3(tau0, tau3, f_lower,
                          in_seconds=False):
    r"""Returns total mass from :math:`\tau_0, \tau_3`."""
    mtotal = (tau3 / _a3(f_lower)) / (tau0 / _a0(f_lower))
    if not in_seconds:
        # convert back to solar mass units
        mtotal /= lal.MTSUN_SI
    return mtotal


def eta_from_tau0_tau3(tau0, tau3, f_lower):
    r"""Returns symmetric mass ratio from :math:`\tau_0, \tau_3`."""
    mtotal = mtotal_from_tau0_tau3(tau0, tau3, f_lower,
                                   in_seconds=True)
    eta = mtotal**(-2./3.) * (_a3(f_lower) / tau3)
    return eta


def mass1_from_tau0_tau3(tau0, tau3, f_lower):
    r"""Returns the primary mass from the given :math:`\tau_0, \tau_3`."""
    mtotal = mtotal_from_tau0_tau3(tau0, tau3, f_lower)
    eta = eta_from_tau0_tau3(tau0, tau3, f_lower)
    return mass1_from_mtotal_eta(mtotal, eta)


def mass2_from_tau0_tau3(tau0, tau3, f_lower):
    r"""Returns the secondary mass from the given :math:`\tau_0, \tau_3`."""
    mtotal = mtotal_from_tau0_tau3(tau0, tau3, f_lower)
    eta = eta_from_tau0_tau3(tau0, tau3, f_lower)
    return mass2_from_mtotal_eta(mtotal, eta)

def lambda_tilde(mass1, mass2, lambda1, lambda2):
    """ The effective lambda parameter

    The mass-weighted dominant effective lambda parameter defined in
    https://journals.aps.org/prd/pdf/10.1103/PhysRevD.91.043002
    """
    m1, ia1 = ensurearray(mass1)
    m2, ia2 = ensurearray(mass2)
    lsum, ia3 = ensurearray(lambda1 + lambda2)
    ldiff, ia4 = ensurearray(lambda1 - lambda2)
    input_is_array = any([ia1, ia2, ia3, ia4])
    mask = m1 < m2
    ldiff[mask] = -ldiff[mask]
    eta = eta_from_mass1_mass2(m1, m2)
    p1 = (lsum) * (1 + 7. * eta - 31 * eta ** 2.0)
    p2 = (1 - 4 * eta)**0.5 * (1 + 9 * eta - 11 * eta ** 2.0) * (ldiff)
    return formatreturn(8.0 / 13.0 * (p1 + p2), input_is_array)

#
# =============================================================================
#
#                           CBC spin functions
#
# =============================================================================
#
def chi_eff(mass1, mass2, spin1z, spin2z):
    """Returns the effective spin from mass1, mass2, spin1z, and spin2z."""
    return (spin1z * mass1 + spin2z * mass2) / (mass1 + mass2)


def chi_a(mass1, mass2, spin1z, spin2z):
    """ Returns the aligned mass-weighted spin difference from mass1, mass2,
    spin1z, and spin2z.
    """
    return (spin2z * mass2 - spin1z * mass1) / (mass2 + mass1)


def chi_p(mass1, mass2, spin1x, spin1y, spin2x, spin2y):
    """Returns the effective precession spin from mass1, mass2, spin1x,
    spin1y, spin2x, and spin2y.
    """
    xi1 = secondary_xi(mass1, mass2, spin1x, spin1y, spin2x, spin2y)
    xi2 = primary_xi(mass1, mass2, spin1x, spin1y, spin2x, spin2y)
    return chi_p_from_xi1_xi2(xi1, xi2)


def phi_a(mass1, mass2, spin1x, spin1y, spin2x, spin2y):
    """ Returns the angle between the in-plane perpendicular spins."""
    phi1 = phi_from_spinx_spiny(primary_spin(mass1, mass2, spin1x, spin2x),
                                primary_spin(mass1, mass2, spin1y, spin2y))
    phi2 = phi_from_spinx_spiny(secondary_spin(mass1, mass2, spin1x, spin2x),
                                secondary_spin(mass1, mass2, spin1y, spin2y))
    return (phi1 - phi2) % (2 * numpy.pi)


def phi_s(spin1x, spin1y, spin2x, spin2y):
    """ Returns the sum of the in-plane perpendicular spins."""
    phi1 = phi_from_spinx_spiny(spin1x, spin1y)
    phi2 = phi_from_spinx_spiny(spin2x, spin2y)
    return (phi1 + phi2) % (2 * numpy.pi)


def chi_eff_from_spherical(mass1, mass2, spin1_a, spin1_polar,
                           spin2_a, spin2_polar):
    """Returns the effective spin using spins in spherical coordinates."""
    spin1z = spin1_a * numpy.cos(spin1_polar)
    spin2z = spin2_a * numpy.cos(spin2_polar)
    return chi_eff(mass1, mass2, spin1z, spin2z)


def chi_p_from_spherical(mass1, mass2, spin1_a, spin1_azimuthal, spin1_polar,
                         spin2_a, spin2_azimuthal, spin2_polar):
    """Returns the effective precession spin using spins in spherical
    coordinates.
    """
    spin1x, spin1y, _ = _spherical_to_cartesian(
        spin1_a, spin1_azimuthal, spin1_polar)
    spin2x, spin2y, _ = _spherical_to_cartesian(
        spin2_a, spin2_azimuthal, spin2_polar)
    return chi_p(mass1, mass2, spin1x, spin1y, spin2x, spin2y)


def primary_spin(mass1, mass2, spin1, spin2):
    """Returns the dimensionless spin of the primary mass."""
    mass1, ia1 = ensurearray(mass1)
    mass2, ia2 = ensurearray(mass2)
    spin1, ia3 = ensurearray(spin1)
    spin2, ia4 = ensurearray(spin2)
    input_is_array = any([ia1, ia2, ia3, ia4])
    if (mass1.shape != mass2.shape) or (mass1.shape != spin1.shape) or (
        mass1.shape != spin2.shape):
        raise ValueError("mass1, mass2, spin1, spin2 must have same shape")
    sp = copy.copy(spin1)
    mask = mass1 < mass2
    sp[mask] = spin2[mask]
    return formatreturn(sp, input_is_array)


def secondary_spin(mass1, mass2, spin1, spin2):
    """Returns the dimensionless spin of the secondary mass."""
    mass1, ia1 = ensurearray(mass1)
    mass2, ia2 = ensurearray(mass2)
    spin1, ia3 = ensurearray(spin1)
    spin2, ia4 = ensurearray(spin2)
    input_is_array = any([ia1, ia2, ia3, ia4])
    if (mass1.shape != mass2.shape) or (mass1.shape != spin1.shape) or (
        mass1.shape != spin2.shape):
        raise ValueError("mass1, mass2, spin1, spin2 must have same shape")
    ss = copy.copy(spin2)
    mask = mass1 < mass2
    ss[mask] = spin1[mask]
    return formatreturn(ss, input_is_array)


def primary_xi(mass1, mass2, spin1x, spin1y, spin2x, spin2y):
    """Returns the effective precession spin argument for the larger mass.
    """
    spinx = primary_spin(mass1, mass2, spin1x, spin2x)
    spiny = primary_spin(mass1, mass2, spin1y, spin2y)
    return chi_perp_from_spinx_spiny(spinx, spiny)


def secondary_xi(mass1, mass2, spin1x, spin1y, spin2x, spin2y):
    """Returns the effective precession spin argument for the smaller mass.
    """
    spinx = secondary_spin(mass1, mass2, spin1x, spin2x)
    spiny = secondary_spin(mass1, mass2, spin1y, spin2y)
    return xi2_from_mass1_mass2_spin2x_spin2y(mass1, mass2, spinx, spiny)


def xi1_from_spin1x_spin1y(spin1x, spin1y):
    """Returns the effective precession spin argument for the larger mass.
    This function assumes it's given spins of the primary mass.
    """
    return chi_perp_from_spinx_spiny(spin1x, spin1y)


def xi2_from_mass1_mass2_spin2x_spin2y(mass1, mass2, spin2x, spin2y):
    """Returns the effective precession spin argument for the smaller mass.
    This function assumes it's given spins of the secondary mass.
    """
    q = q_from_mass1_mass2(mass1, mass2)
    a1 = 2 + 3 * q / 2
    a2 = 2 + 3 / (2 * q)
    return a1 / (q**2 * a2) * chi_perp_from_spinx_spiny(spin2x, spin2y)


def chi_perp_from_spinx_spiny(spinx, spiny):
    """Returns the in-plane spin from the x/y components of the spin.
    """
    return numpy.sqrt(spinx**2 + spiny**2)


def chi_perp_from_mass1_mass2_xi2(mass1, mass2, xi2):
    """Returns the in-plane spin from mass1, mass2, and xi2 for the
    secondary mass.
    """
    q = q_from_mass1_mass2(mass1, mass2)
    a1 = 2 + 3 * q / 2
    a2 = 2 + 3 / (2 * q)
    return q**2 * a2 / a1 * xi2


def chi_p_from_xi1_xi2(xi1, xi2):
    """Returns effective precession spin from xi1 and xi2.
    """
    xi1, ia1 = ensurearray(xi1)
    xi2, ia2 = ensurearray(xi2)
    input_is_array = ia1 or ia2
    if xi1.shape != xi2.shape:
        raise ValueError("xi1, xi2 must have same shape")
    chi_p = copy.copy(xi1)
    mask = xi1 < xi2
    chi_p[mask] = xi2[mask]
    return formatreturn(chi_p, input_is_array)


def phi1_from_phi_a_phi_s(phi_a, phi_s):
    """Returns the angle between the x-component axis and the in-plane
    spin for the primary mass from phi_s and phi_a.
    """
    return (phi_s + phi_a) / 2.0


def phi2_from_phi_a_phi_s(phi_a, phi_s):
    """Returns the angle between the x-component axis and the in-plane
    spin for the secondary mass from phi_s and phi_a.
    """
    return (phi_s - phi_a) / 2.0


def phi_from_spinx_spiny(spinx, spiny):
    """Returns the angle between the x-component axis and the in-plane spin.
    """
    phi = numpy.arctan2(spiny, spinx)
    return phi % (2 * numpy.pi)


def spin1z_from_mass1_mass2_chi_eff_chi_a(mass1, mass2, chi_eff, chi_a):
    """Returns spin1z.
    """
    return (mass1 + mass2) / (2.0 * mass1) * (chi_eff - chi_a)


def spin2z_from_mass1_mass2_chi_eff_chi_a(mass1, mass2, chi_eff, chi_a):
    """Returns spin2z.
    """
    return (mass1 + mass2) / (2.0 * mass2) * (chi_eff + chi_a)


def spin1x_from_xi1_phi_a_phi_s(xi1, phi_a, phi_s):
    """Returns x-component spin for primary mass.
    """
    phi1 = phi1_from_phi_a_phi_s(phi_a, phi_s)
    return xi1 * numpy.cos(phi1)


def spin1y_from_xi1_phi_a_phi_s(xi1, phi_a, phi_s):
    """Returns y-component spin for primary mass.
    """
    phi1 = phi1_from_phi_a_phi_s(phi_s, phi_a)
    return xi1 * numpy.sin(phi1)


def spin2x_from_mass1_mass2_xi2_phi_a_phi_s(mass1, mass2, xi2, phi_a, phi_s):
    """Returns x-component spin for secondary mass.
    """
    chi_perp = chi_perp_from_mass1_mass2_xi2(mass1, mass2, xi2)
    phi2 = phi2_from_phi_a_phi_s(phi_a, phi_s)
    return chi_perp * numpy.cos(phi2)


def spin2y_from_mass1_mass2_xi2_phi_a_phi_s(mass1, mass2, xi2, phi_a, phi_s):
    """Returns y-component spin for secondary mass.
    """
    chi_perp = chi_perp_from_mass1_mass2_xi2(mass1, mass2, xi2)
    phi2 = phi2_from_phi_a_phi_s(phi_a, phi_s)
    return chi_perp * numpy.sin(phi2)


def dquadmon_from_lambda(lambdav):
    r"""Return the quadrupole moment of a neutron star given its lambda

    We use the relations defined here. https://arxiv.org/pdf/1302.4499.pdf.
    Note that the convention we use is that:

    .. math::

        \mathrm{dquadmon} = \bar{Q} - 1.

    Where :math:`\bar{Q}` (dimensionless) is the reduced quadrupole moment.
    """
    ll = numpy.log(lambdav)
    ai = .194
    bi = .0936
    ci = 0.0474
    di = -4.21 * 10**-3.0
    ei = 1.23 * 10**-4.0
    ln_quad_moment = ai + bi*ll + ci*ll**2.0 + di*ll**3.0 + ei*ll**4.0
    return numpy.exp(ln_quad_moment) - 1

#
# =============================================================================
#
#                         Extrinsic parameter functions
#
# =============================================================================
#
def chirp_distance(dist, mchirp, ref_mass=1.4):
    """Returns the chirp distance given the luminosity distance and chirp mass.
    """
    return dist * (2.**(-1./5) * ref_mass / mchirp)**(5./6)


def distance_from_chirp_distance_mchirp(chirp_distance, mchirp, ref_mass=1.4):
    """Returns the luminosity distance given a chirp distance and chirp mass.
    """
    return chirp_distance * (2.**(-1./5) * ref_mass / mchirp)**(-5./6)


def _det_tc(detector_name, ra, dec, tc, ref_frame='geocentric'):
    """Returns the coalescence time of a signal in the given detector.

    Parameters
    ----------
    detector_name : string
        The name of the detector, e.g., 'H1'.
    ra : float
        The right ascension of the signal, in radians.
    dec : float
        The declination of the signal, in radians.
    tc : float
        The GPS time of the coalescence of the signal in the `ref_frame`.
    ref_frame : {'geocentric', string}
        The reference frame that the given coalescence time is defined in.
        May specify 'geocentric', or a detector name; default is 'geocentric'.

    Returns
    -------
    float :
        The GPS time of the coalescence in detector `detector_name`.
    """
    if ref_frame == detector_name:
        return tc
    detector = Detector(detector_name)
    if ref_frame == 'geocentric':
        return tc + detector.time_delay_from_earth_center(ra, dec, tc)
    else:
        other = Detector(ref_frame)
        return tc + detector.time_delay_from_detector(other, ra, dec, tc)

det_tc = numpy.vectorize(_det_tc)

def _optimal_orientation_from_detector(detector_name, tc):
    """ Low-level function to be called from _optimal_dec_from_detector
    and _optimal_ra_from_detector"""

    d = Detector(detector_name)
    ra, dec = d.optimal_orientation(tc)

    return ra, dec


def _optimal_dec_from_detector(detector_name, tc):
    """For a given detector and GPS time, return the optimal orientation
    (directly overhead of the detector) in declination.


    Parameters
    ----------
    detector_name : string
        The name of the detector, e.g., 'H1'.
    tc : float
        The GPS time of the coalescence of the signal in the `ref_frame`.

    Returns
    -------
    float :
        The declination of the signal, in radians.
    """
    return _optimal_orientation_from_detector(detector_name, tc)[1]


optimal_dec_from_detector = numpy.vectorize(_optimal_dec_from_detector)


def _optimal_ra_from_detector(detector_name, tc):
    """For a given detector and GPS time, return the optimal orientation
    (directly overhead of the detector) in right ascension.


    Parameters
    ----------
    detector_name : string
        The name of the detector, e.g., 'H1'.
    tc : float
        The GPS time of the coalescence of the signal in the `ref_frame`.

    Returns
    -------
    float :
        The declination of the signal, in radians.
    """
    return _optimal_orientation_from_detector(detector_name, tc)[0]


optimal_ra_from_detector = numpy.vectorize(_optimal_ra_from_detector)


#
# =============================================================================
#
#                         Likelihood statistic parameter functions
#
# =============================================================================
#
def snr_from_loglr(loglr):
    """Returns SNR computed from the given log likelihood ratio(s). This is
    defined as `sqrt(2*loglr)`.If the log likelihood ratio is < 0, returns 0.

    Parameters
    ----------
    loglr : array or float
        The log likelihood ratio(s) to evaluate.

    Returns
    -------
    array or float
        The SNRs computed from the log likelihood ratios.
    """
    singleval = isinstance(loglr, float)
    if singleval:
        loglr = numpy.array([loglr])
    # temporarily quiet sqrt(-1) warnings
    numpysettings = numpy.seterr(invalid='ignore')
    snrs = numpy.sqrt(2*loglr)
    numpy.seterr(**numpysettings)
    snrs[numpy.isnan(snrs)] = 0.
    if singleval:
        snrs = snrs[0]
    return snrs

#
# =============================================================================
#
#                         BH Ringdown functions
#
# =============================================================================
#
def get_lm_f0tau(mass, spin, l, m, nmodes):
    """Return the f_0 and the tau of each overtone for a given lm mode
    """
    qnmfreq = lal.CreateCOMPLEX16Vector(nmodes)
    lalsim.SimIMREOBGenerateQNMFreqV2fromFinal(
        qnmfreq, float(mass), float(spin), l, m, nmodes)
    f_0 = [qnmfreq.data[n].real / (2 * numpy.pi) for n in range(nmodes)]
    tau = [1. / qnmfreq.data[n].imag for n in range(nmodes)]
    return f_0, tau


def freq_from_final_mass_spin(final_mass, final_spin, l=2, m=2):
    return get_lm_f0tau(final_mass, final_spin, l, m, 1)[0][0]


def tau_from_final_mass_spin(final_mass, final_spin, l=2, m=2):
    return get_lm_f0tau(final_mass, final_spin, l, m, 1)[1][0]

#
# =============================================================================
#
#                         Math helper functions
#
# =============================================================================
#
def return_base10_log(x):
    """
    Simply return the log base 10 of the input.
    Parameters
    ----------
    x: float or array
    """
    x, ia1 = ensurearray(x)
    return formatreturn(numpy.log10(x), ia1)



#
# =============================================================================
#
#                         post-Newtonian functions
#
# =============================================================================
#

def velocity_to_frequency(v, M):
    """ Calculate the gravitational-wave frequency from the
    total mass and invariant velocity.
    Parameters
    ----------
    v: float
        Invariant velocity
    M: float
        Binary total mass
    """
    return v**(3.0) / (M * lal.MTSUN_SI * lal.PI)

def frequency_to_velocity(f, M):
    """ Calculate the invariant velocity from the total
    mass and gravitational-wave frequency.
    Parameters
    ----------
    f: float
        Gravitational-wave frequency
    M: float
        Binary total mass
    """
    return (lal.PI * M * lal.MTSUN_SI * f)**(1.0/3.0)

def f_schwarzchild_isco(M):
    """
    Innermost stable circular orbit (ISCO) for a test particle
    orbiting a Schwarzschild black hole

    Parameters
    ----------
    M : float or numpy.array
        Total mass in solar mass units

    Returns
    -------
    f : float or numpy.array
        Frequency in Hz
    """
    return velocity_to_frequency((1.0/6.0)**(0.5), M)


#
# ============================================================================
#
#                          p-g mode non-linear tide functions
#
# ============================================================================
#

def nltides_coefs(amplitude, n, m1, m2):
    """Calculate the coefficents needed to compute the
    shift in t(f) and phi(f) due to non-linear tides.

    Parameters
    ----------
    f0: float
        Frequency that NL effects switch on
    amplitude: float
        Amplitude of effect
    n: float
        Growth dependence of effect
    m1: float
        Mass of component 1
    m2: float
        Mass of component 2
    """

    # Use 100.0 Hz as a reference frequency
    f_ref = 100.0

    # Calculate chirp mass
    mc = mchirp_from_mass1_mass2(m1, m2)
    mc *= lal.lal.MSUN_SI

    # Calculate constants in phasing
    a = (96./5.) * \
        (lal.lal.G_SI * lal.lal.PI * mc * f_ref / lal.lal.C_SI**3.)**(5./3.)
    b = 6. * amplitude
    t_of_f_factor = -1./(lal.lal.PI*f_ref) * b/(a*a * (n-4.))
    phi_of_f_factor = -2.*b / (a*a * (n-3.))

    return f_ref, t_of_f_factor, phi_of_f_factor

def nltides_gw_phase_difference(f, f0, amplitude, n, m1, m2):
    """Calculate the gravitational-wave phase shift bwtween
    f and f_coalescence = infinity due to non-linear tides.
    To compute the phase shift between e.g. f_low and f_isco,
    call this function twice and compute the difference.

    Parameters
    ----------
    f: float
        Frequency from which to compute phase
    f0: float
        Frequency that NL effects switch on
    amplitude: float
        Amplitude of effect
    n: float
        Growth dependence of effect
    m1: float
        Mass of component 1
    m2: float
        Mass of component 2
    """

    f, ia1 = ensurearray(f)
    f0, ia2 = ensurearray(f0)
    amplitude, ia3 = ensurearray(amplitude)
    n, ia4 = ensurearray(n)
    m1, ia5 = ensurearray(m1)
    m2, ia6 = ensurearray(m2)

    if f.shape != f0.shape:
        raise ValueError("f, f0 must have same shape")
    if f.shape != amplitude.shape:
        raise ValueError("f, amplitude must have same shape")
    if f.shape != n.shape:
        raise ValueError("f, n must have same shape")
    if f.shape != m1.shape:
        raise ValueError("f, m1 must have same shape")
    if f.shape != m2.shape:
        raise ValueError("f, m2 must have same shape")

    input_is_array = any([ia1, ia2, ia3, ia4, ia5, ia6])

    delta_phi = numpy.zeros(m1.shape)

    f_ref, _, phi_of_f_factor = nltides_coefs(amplitude, n, m1, m2)

    mask = f <= f0
    delta_phi[mask] = - phi_of_f_factor[mask] * (f0[mask]/f_ref)**(n[mask]-3.)

    mask = f > f0
    delta_phi[mask] = - phi_of_f_factor[mask] * (f[mask]/f_ref)**(n[mask]-3.)

    return formatreturn(delta_phi,input_is_array)

def nltides_gw_phase_diff_isco(f_low, f0, amplitude, n, m1, m2):
    """Calculate the gravitational-wave phase shift bwtween
    f_low and f_isco due to non-linear tides.
    Parameters
    ----------
    f_low: float
        Frequency from which to compute phase. If the other
        arguments are passed as numpy arrays then the value
        of f_low is duplicated for all elements in the array
    f0: float or array
        Frequency that NL effects switch on
    amplitude: float or array
        Amplitude of effect
    n: float or array
        Growth dependence of effect
    m1: float or array
        Mass of component 1
    m2: float or array
        Mass of component 2
    """
    
    f0, ia1 = ensurearray(f0)
    amplitude, ia2 = ensurearray(amplitude)
    n, ia3 = ensurearray(n)
    m1, ia4 = ensurearray(m1)
    m2, ia5 = ensurearray(m2)

    if f0.shape != amplitude.shape:
        raise ValueError("f0, amplitude must have same shape")
    if f0.shape != n.shape:
        raise ValueError("f0, n must have same shape")
    if f0.shape != m1.shape:
        raise ValueError("f0, m1 must have same shape")
    if f0.shape != m2.shape:
        raise ValueError("f0, m2 must have same shape")

    input_is_array = any([ia1, ia2, ia3, ia4, ia5])

    f_low = numpy.zeros(m1.shape) + f_low

    phi_l = nltides_gw_phase_difference(
                f_low, f0, amplitude, n, m1, m2)

    f_isco = f_schwarzchild_isco(m1+m2)

    phi_i = nltides_gw_phase_difference(
                f_isco, f0, amplitude, n, m1, m2)

    return formatreturn(phi_i - phi_l, input_is_array)


__all__ = ['dquadmon_from_lambda', 'lambda_tilde', 'primary_mass',
           'secondary_mass', 'mtotal_from_mass1_mass2',
           'q_from_mass1_mass2', 'invq_from_mass1_mass2',
           'eta_from_mass1_mass2', 'mchirp_from_mass1_mass2',
           'mass1_from_mtotal_q', 'mass2_from_mtotal_q',
           'mass1_from_mtotal_eta', 'mass2_from_mtotal_eta',
           'mtotal_from_mchirp_eta', 'mass1_from_mchirp_eta',
           'mass2_from_mchirp_eta', 'mass2_from_mchirp_mass1',
           'mass_from_knownmass_eta', 'mass2_from_mass1_eta',
           'mass1_from_mass2_eta', 'eta_from_q', 'mass1_from_mchirp_q',
           'mass2_from_mchirp_q', 'tau0_from_mtotal_eta',
           'tau3_from_mtotal_eta', 'tau0_from_mass1_mass2',
           'tau3_from_mass1_mass2', 'mtotal_from_tau0_tau3',
           'eta_from_tau0_tau3', 'mass1_from_tau0_tau3',
           'mass2_from_tau0_tau3', 'primary_spin', 'secondary_spin',
           'chi_eff', 'chi_a', 'chi_p', 'phi_a', 'phi_s',
           'primary_xi', 'secondary_xi',
           'xi1_from_spin1x_spin1y', 'xi2_from_mass1_mass2_spin2x_spin2y',
           'chi_perp_from_spinx_spiny', 'chi_perp_from_mass1_mass2_xi2',
           'chi_p_from_xi1_xi2', 'phi_from_spinx_spiny',
           'phi1_from_phi_a_phi_s', 'phi2_from_phi_a_phi_s',
           'spin1z_from_mass1_mass2_chi_eff_chi_a',
           'spin2z_from_mass1_mass2_chi_eff_chi_a',
           'spin1x_from_xi1_phi_a_phi_s', 'spin1y_from_xi1_phi_a_phi_s',
           'spin2x_from_mass1_mass2_xi2_phi_a_phi_s',
           'spin2y_from_mass1_mass2_xi2_phi_a_phi_s',
           'chirp_distance', 'det_tc', 'snr_from_loglr',
           'freq_from_final_mass_spin', 'tau_from_final_mass_spin',
           'optimal_dec_from_detector','optimal_ra_from_detector',
           'chi_eff_from_spherical', 'chi_p_from_spherical',
           'return_base10_log'
           'nltides_gw_phase_diff_isco'
          ]
