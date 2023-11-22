from collections import defaultdict
from math import log

import pandas as pd


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


def cosine_similarity(spectrum1, spectrum2):
    """
    Calculates the cosine similarity, based on code I got from Alex,
    which is in turn based on the paper "Optimization & Testing of Mass
    Spectral Library Search Algorithms for Compound Identification" by
    Stein & Scott.
    """
    df1 = pd.DataFrame(spectrum1, columns=["mz", "intensity"])
    df2 = pd.DataFrame(spectrum2, columns=["mz", "intensity"])
    df1["binned_mz"] = df1["mz"].apply(round, ndigits=0)
    df2["binned_mz"] = df2["mz"].apply(round, ndigits=0)
    merged_df = pd.merge(df1, df2, on="binned_mz", how="outer")

    # The merge renames the mz columns to keep them distinct -- mz_x is
    # the mz column from df1, and mz_y is from df2
    merged_df["mz_delta"] = abs(merged_df["mz_x"] - merged_df["mz_y"])
    merged_df["mz_x"].fillna(merged_df["mz_y"], inplace=True)
    merged_df["mz_y"].fillna(merged_df["mz_x"], inplace=True)
    merged_df.fillna(0, inplace=True)
    merged_df.sort_values(by="mz_delta", ascending=True, inplace=True)

    aligned_df = merged_df[(~merged_df.duplicated(subset="mz_x", keep="first")) & (~merged_df.duplicated(subset="mz_y", keep="first"))].copy()
    aligned_df.drop(["binned_mz", "mz_delta"], axis=1, inplace=True)
    aligned_df.sort_values(by="mz_x", inplace=True)
    aligned_df.reset_index(drop=True, inplace=True)

    # m and n are values found by trial and error in Stein & Scott's
    # paper to be a useful adjustment to the calculation
    m, n = 0.5, 0.5
    aligned_df["weighted_x"] = aligned_df["mz_x"].pow(m) * aligned_df["intensity_x"].pow(n)
    aligned_df["weighted_y"] = aligned_df["mz_y"].pow(m) * aligned_df["intensity_y"].pow(n)
    numerator = sum(aligned_df["weighted_x"] * aligned_df["weighted_y"]) ** 2
    denominator = sum(aligned_df["weighted_x"].pow(2)) * sum(aligned_df["weighted_y"].pow(2))
    return numerator/denominator



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
        mz, intensity = spectrum_copy[i]
        if intensity > 0:
            # either use the absolute error (da_error) or parts per million of the peak mz (ppm_error)
            # if neither input is good, assume no delta, though this should probably be improved later
            if da_error and da_error > 0:
                mz_window_size = da_error
            elif ppm_error > 0:
                mz_window_size = ppm_error * 1e-6 * mz
            else:
                mz_window_size = 0

            # find lowest mz within window
            lowest_mz_peak_index = i
            while lowest_mz_peak_index > 0:
                mz_delta = mz - spectrum_copy[lowest_mz_peak_index-1][0]
                if mz_delta <= mz_window_size:
                    lowest_mz_peak_index -= 1
                else:
                    break
            
            # find highest mz within window
            highest_mz_peak_index = i
            while highest_mz_peak_index < len(spectrum_copy)-1:
                mz_delta = spectrum_copy[highest_mz_peak_index+1][0] - mz
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


def validate_spectrum(spectrum):
    if type(spectrum) is not list:
        raise ValueError("Spectrum format is incorrect -- submitted value is not a list")
    if not all((type(x) is tuple or type(x) is list) for x in spectrum):
        raise ValueError("Spectrum format is incorrect -- at least one element in the list of peaks is not itself a list.")
    if not all(len(x) == 2 for x in spectrum):
        raise ValueError("Spectrum format is incorrect -- at least one element in the list does not have exactly two elements (m/z and intensity).")
    if not all(isinstance(x[0], (int, float)) and isinstance(x[1], (int, float)) for x in spectrum):
        raise ValueError("Spectrum format is incorrect -- at least one peak in the list has a non-numeric object in its data.")