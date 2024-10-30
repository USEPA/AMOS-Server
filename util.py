from copy import deepcopy
import csv
import io
import re

import pandas as pd

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


def make_csv_string(data_rows):
    """
    Takes a list of dictionaries of the same type and translates them into a
    single CSV string.
    """
    f = io.StringIO("")
    writer = csv.DictWriter(f, fieldnames=data_rows[0].keys())
    writer.writeheader()
    writer.writerows(data_rows)
    return f.getvalue()


def make_excel_file(df_dict):
    """
    Constructs an in-memory Excel file using the specified dictionary of data
    frames.  Keys will be used as the sheet names while the values should be the
    data frames to store.
    """
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer) as writer:
        for sheet_name, df in df_dict.items():
            df.to_excel(writer, sheet_name=sheet_name, index=None)
    
    return buffer.getvalue()


def merge_substance_info_and_counts(substance_info, count_info):
    """
    Combines the information from a list of identifiers for a substance with a
    list of record counts in the database for that substance.

    Assumes that there are elements in the count_info dictionary named 'Fact
    Sheet', 'Method', and 'Spectrum', and that both dictionaries have a
    'dtxsid' field to link between the two.
    """

    all_info = deepcopy(substance_info)
    for substance in all_info:
        records = count_info[substance["dtxsid"]]
        substance["methods"] = records.get("Method", 0)
        substance["fact_sheets"] = records.get("Fact Sheet", 0)
        substance["spectra"] = records.get("Spectrum", 0)
    return all_info
