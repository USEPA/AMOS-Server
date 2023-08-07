from collections import defaultdict
from math import log


def calculate_entropy_similarity(spectrum_a, spectrum_b, da_error=None, ppm_error=None):
    """
    Calculates the entropy similarity for two given spectra.
    """
    if (da_error is None) and (ppm_error is None):
        da_error = 0.05

    spectrum_a = normalize_spectrum(spectrum_a)
    spectrum_b = normalize_spectrum(spectrum_b)

    combined_dict = defaultdict(float)
    for mz, i in spectrum_a + spectrum_b:
        combined_dict[mz] += i
    combined_spectrum = [list(i) for i in list(combined_dict.items())]

    spectrum_a = combine_peaks(spectrum_a, da_error, ppm_error)
    spectrum_b = combine_peaks(spectrum_b, da_error, ppm_error)
    combined_spectrum = combine_peaks(combined_spectrum, da_error, ppm_error)

    sAB = calculate_spectral_entropy(combined_spectrum)
    sA = calculate_spectral_entropy(spectrum_a)
    sB = calculate_spectral_entropy(spectrum_b)
    similarity =  1 - (2 * sAB - sA - sB)/log(4)

    # This is to try to keep floating point errors from sending back tiny
    # negative values
    if abs(similarity) < 1e-9:
        return 0

    return similarity


def calculate_spectral_entropy(spectrum):
    """
    Calculates the spectral entropy for a single spectrum.
    """
    total_intensity = sum([i for mz, i in spectrum])
    scaled_intensities = [i/total_intensity for mz, i in spectrum]
    return sum([-1 * i * log(i) for i in scaled_intensities])


def combine_peaks(spectrum, da_error=0.05, ppm_error=None):
    """
    Combines the peaks of a spectrum that are within a certain margin of error
    of each other.  Selection of which peaks to starts with finding the highest-
    intensity peak that hasn't been merged, combining sufficiently close peaks,
    and repeating until all peaks have been considered
    """
    # Create a copy of the spectrum & sort it in order of increasing m/z.
    spectrum_copy = spectrum.copy()
    spectrum_copy.sort()

    # Find order of elements by decreasing intensity.
    intensity_order = [i[0] for i in sorted(enumerate(spectrum_copy), key=lambda x: -x[1][1])]

    # Start a new, empty array, called spec_new.
    spec_new = []

    for i in intensity_order:
        peak_under_consideration = spectrum_copy[i]
        if peak_under_consideration[1] > 0:
            # either use the absolute error (da_error) or parts per million of the peak mz (ppm_error)
            # if neither input is good, assume no delta, though this should probably be improved later
            if da_error and da_error > 0:
                mz_window_size = da_error
            elif ppm_error > 0:
                mz_window_size = ppm_error * 1e-6 * peak_under_consideration
            else:
                mz_window_size = 0

            lowest_mz_peak_index = i
            while lowest_mz_peak_index > 0:
                mz_delta = peak_under_consideration[0] - spectrum_copy[lowest_mz_peak_index-1][0]
                if mz_delta <= mz_window_size:
                    lowest_mz_peak_index -= 1
                else:
                    break

            highest_mz_peak_index = i
            while highest_mz_peak_index < len(spectrum_copy)-1:
                mz_delta = spectrum_copy[highest_mz_peak_index+1][0] - peak_under_consideration[0]
                if mz_delta <= mz_window_size:
                    highest_mz_peak_index += 1
                else:
                    break

            intensity_sum = 0
            intensity_weighted_sum = 0
            for idx in range(lowest_mz_peak_index, highest_mz_peak_index+1):
                intensity_sum += spectrum_copy[idx][1]
                intensity_weighted_sum += spectrum_copy[idx][0] * spectrum_copy[idx][1]
                spectrum_copy[idx][1] = 0

            spec_new.append([intensity_weighted_sum/intensity_sum, intensity_sum])
    
    spec_new.sort()
    return spec_new


def normalize_spectrum(spectrum):
    """
    Rescales a spectrum so that the max intensity is 1.
    """
    max_intensity = sum([i for mz, i in spectrum])
    normalized_spectrum = [[mz, i/max_intensity] for mz, i in spectrum]
    return normalized_spectrum