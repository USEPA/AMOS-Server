from collections import defaultdict
import csv
import io
from math import log
import re

def clean_year(year_value):
    """
    Convenience function intended to take care of showing just the year of date
    strings with various possible formats.

    NOTE: unsure whether the behavior for unknown date format should be
    just returning the value, or returning a blank or something.

    Parameters
    ----------
    year_value : string
        A date in string form.  Currently should be either a four-digit year or
        a one/two-digit month followed by a four-digit year.

    Returns
    -------
    Either None (if the input was None), the year (if the string could be
    parsed), or the original value (if it couldn't be parsed).

    """
    if year_value is None:
        return None
    elif re.match("^[0-9]{4}-[01][0-9]-[0-3][0-9]$", year_value):
        return int(year_value[:4])
    elif re.match("^[0-9]{4}$", year_value):
        return int(year_value)
    elif re.match("^([0-9]+/)?[0-9]+/[0-9]{4}$", year_value):
        return int(year_value[-4:])
    else:
        print(f"Issue with year value {year_value} -- unclear string format")
        return year_value


def calculate_spectral_entropy(spectrum):
    total_intensity = sum([i for mz, i in spectrum])
    scaled_intensities = [i/total_intensity for mz, i in spectrum]
    return sum([-1 * i * log(i) for i in scaled_intensities])


def calculate_entropy_similarity(spectrum_a, spectrum_b):
    combined_dict = defaultdict(list)
    [combined_dict[mz].append(i) for mz, i in spectrum_a]
    [combined_dict[mz].append(i) for mz, i in spectrum_b]
    combined_spectrum = [[k, sum(v)] for k,v in combined_dict.items()]

    sAB = calculate_spectral_entropy(combined_spectrum)
    sA = calculate_spectral_entropy(spectrum_a)
    sB = calculate_spectral_entropy(spectrum_b)
    return 1 - (2 * sAB - sA - sB)/log(4)


def make_csv_string(data_rows):
    f = io.StringIO("")
    writer = csv.DictWriter(f, fieldnames=data_rows[0].keys())
    writer.writeheader()
    writer.writerows(data_rows)
    return f.getvalue()