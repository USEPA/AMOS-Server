import argparse
import json
import os

import pytesseract
from pdf2image import convert_from_path
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
from tqdm import tqdm

from table_definitions import FactSheets, Methods, SpectrumPDFs, AnalyticalQC


# https://coderpad.io/blog/development/sqlalchemy-with-postgresql/

def save_methods(session):
    os.makedirs("methods", exist_ok=True)
    with tqdm(total=session.query(Methods).count(), desc="Methods") as pb:
        for row in session.query(Methods).yield_per(10):
            with open(os.path.join("methods", f"{row.internal_id}.pdf"), "wb") as file:
                file.write(row.pdf_data)

            with open(os.path.join("methods", f"{row.internal_id}.json"), "w") as file:
                js = row.pdf_metadata or {}
                js["date_published"] = row.date_published
                js["method_name"] = row.method_name
                js["method_number"] = row.method_number
                js["analyte"] = list(s.strip() for s in (row.analyte or "").split(";"))
                js["functional_classes"] = list(s.strip() for s in (row.functional_classes or "").split(";"))
                js["matrix"] = row.matrix
                js["document_type"] = row.document_type
                js["publisher"] = row.publisher
                js["mmdb_matrix"] = row.mmdb_matrix
                json.dump(js, file, indent=4)

            pb.update()


def save_fact_sheets(session):
    os.makedirs("fact_sheets", exist_ok=True)
    with tqdm(total=session.query(FactSheets).count(), desc="Fact sheets") as pb:
        for row in session.query(FactSheets).yield_per(10):
            with open(os.path.join("fact_sheets", f"{row.internal_id}.pdf"), "wb") as file:
                file.write(row.pdf_data)

            with open(os.path.join("fact_sheets", f"{row.internal_id}.json"), "w") as file:
                js = row.pdf_metadata or {}
                js["fact_sheet_name"] = row.fact_sheet_name
                js["document_type"] = row.document_type
                js["analyte"] = list(s.strip() for s in (row.analyte or "").split(";"))
                js["functional_classes"] = list(s.strip() for s in (row.functional_classes or "").split(";"))
                json.dump(js, file, indent=4)

            pb.update()


def save_spectra(session):
    os.makedirs("spectra", exist_ok=True)
    with tqdm(total=session.query(SpectrumPDFs).count(), desc="Spectra") as pb:
        for row in session.query(SpectrumPDFs).yield_per(10):
            with open(os.path.join("spectra", f"{row.internal_id}.pdf"), "wb") as file:
                file.write(row.pdf_data)

            with open(os.path.join("spectra", f"{row.internal_id}.json"), "w") as file:
                js = row.pdf_metadata or {}
                json.dump(js, file, indent=4)

            pb.update()


def save_analytical_qc(session):
    os.makedirs("analytical_qc", exist_ok=True)
    with tqdm(total=session.query(AnalyticalQC).count(), desc="Analytical QC") as pb:
        for row in session.query(AnalyticalQC).yield_per(10):
            with open(os.path.join("analytical_qc", f"{row.internal_id}.pdf"), "wb") as file:
                file.write(row.pdf_data)

            with open(os.path.join("analytical_qc", f"{row.internal_id}.json"), "w") as file:
                js = row.pdf_metadata or {}
                js["filename"] = row.filename
                js["experiment_date"] = row.experiment_date
                js["timepoint"] = row.timepoint
                js["batch"] = row.batch
                js["well"] = row.well
                js["first_timepoint"] = row.first_timepoint
                js["last_timepoint"] = row.last_timepoint
                js["stability_call"] = row.stability_call
                js["tox21_id"] = row.tox21_id
                js["pubchem_sid"] = row.pubchem_sid
                js["bottle_barcode"] = row.bottle_barcode
                js["annotation"] = row.annotation
                js["sample_id"] = row.sample_id
                js["flags"] = list(s.strip() for s in (row.flags or "").split(";"))
                js["lcms_amen_pos_true"] = row.lcms_amen_pos_true
                js["lcms_amen_neg_true"] = row.lcms_amen_neg_true
                json.dump(js, file, indent=4)

            pb.update()


def export(args):
    url = URL.create(
        drivername="postgresql+psycopg2",
        username="postgres",
        password="qqq123",
        host="127.0.0.1",
        database="amos"
    )
    engine = create_engine(url)
    conn = engine.connect()
    Session = sessionmaker(bind=engine)
    with Session() as session:
        if 'methods' in args.objects:
            save_methods(session)
        if 'fact_sheets' in args.objects:
            save_fact_sheets(session)
        if 'spectra' in args.objects:
            save_spectra(session)
        if 'analytical_qc' in args.objects:
            save_analytical_qc(session)


def extract(args):
    pages = convert_from_path(args.input)
    text = ''
    for page in pages:
        text += pytesseract.image_to_string(page) + '\n'
    print(text)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest='command', required=True)

    parser_export = subparsers.add_parser('export')
    parser_export.add_argument('-o', '--objects', nargs="+", required=False,
                               choices=['methods', 'fact_sheets', 'spectra', 'analytical_qc'],
                               default=['methods', 'fact_sheets', 'spectra', 'analytical_qc'], type=str)

    parser_export = subparsers.add_parser('extract')
    parser_export.add_argument('-i', '--input', type=str, required=True)
    parser_export.add_argument('-o', '--output', type=str)

    args = parser.parse_args()

    if args.command == 'export':
        export(args)
    elif args.command == 'extract':
        extract(args)
    else:
        parser.print_usage()
