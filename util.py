import csv
import io
import re

from flask import Response
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
    f = io.StringIO("")
    writer = csv.DictWriter(f, fieldnames=data_rows[0].keys())
    writer.writeheader()
    writer.writerows(data_rows)
    return f.getvalue()


def make_excel_file(df_dict):
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer) as writer:
        for sheet_name, df in df_dict.items():
            df.to_excel(writer, sheet_name=sheet_name, index=None)
    
    return buffer.getvalue()
