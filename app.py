from collections import Counter, defaultdict
from enum import Enum
import io
import re
import os

from flask import Flask, jsonify, make_response, request, Response
from flask_cors import CORS
import pandas as pd
import requests
from sqlalchemy import func

import spectrum
from table_definitions import db, SubstanceImages, Substances, Contents, FactSheets, \
    Methods, MethodsWithSpectra, RecordInfo, SpectrumData, SpectrumPDFs, Synonyms
import util
import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration

# Integrating Sentry into Amos
sentry_sdk.init(
    dsn="https://712871757f0243ee8370d9558bfff1ac@ccte-app-monitoring.epa.gov/13",
    integrations=[
        FlaskIntegration(),
    ],

    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for performance monitoring.
    # We recommend adjusting this value in production.
    traces_sample_rate=1.0
)

# load info for PostgreSQL access
uname = os.environ['AMOS_POSTGRES_USER']
pwd = os.environ['AMOS_POSTGRES_PASSWORD']

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = f"postgresql+psycopg2://{uname}:{pwd}@ccte-pgsql-stg.epa.gov:5432/dev_poc"

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = "secretkey"

CORS(app, resources={r'/*': {'origins': '*'}})



class SearchType(Enum):
    InChIKey = 1
    CASRN = 2
    SubstanceName = 3
    DTXSID = 4


def determine_search_type(search_term):
    """
    Determine whether the search term in question is an InChIKey, CAS number, or
    a name.

    Parameters
    ----------
    search_term : string
        String used for searching.

    Returns
    -------
    SearchType enum.

    """
    
    if re.match("^[0-9]*-[0-9]*-[0-9]", search_term.strip()):
        return SearchType.CASRN
    elif re.match("^[A-Z]{14}-[A-Z]{8}[SN][A-Z]-[A-Z]$", search_term.strip()):
        return SearchType.InChIKey
    elif re.match("DTXSID[0-9]*", search_term.strip()):
        return SearchType.DTXSID
    else:
        return SearchType.SubstanceName


@app.route("/get_substances_for_search_term/<search_term>")
def get_substances_for_search_term(search_term):
    """
    Takes a string containing a search term, and tries to find any DTXSIDs that
    match it, returning them along with information about the substances.

    If no DTXSID is found, the function returns None.  If multiple synonyms or
    the first blocks of multiple InChIKeys are matched, the ambiguity variable
    will be passed indicating the issue, along with a list of the substances
    and information about them.

    Parameters
    ----------
    search_term : string
        String used for searching.

    Returns
    -------
    Either the DTXSID corresponding to the searched term, or None if no match
    was found.
    """
    search_type = determine_search_type(search_term)
    substances = None   # default value
    ambiguity = None   # default value
    q = db.select(Substances)

    if search_type == SearchType.DTXSID:
        q = q.filter(Substances.dtxsid == search_term)
        results = db.session.execute(q).first()
        if results:
            substances = results[0].get_row_contents()
    
    elif search_type == SearchType.SubstanceName:
        q_name = q.filter(Substances.preferred_name.ilike(search_term))
        results = db.session.execute(q_name).first()
        # if no matches, check if it's a synonym
        if results:
            substances = results[0].get_row_contents()
        else:
            q_syn = q.join_from(Synonyms, Substances, Synonyms.dtxsid==Substances.dtxsid).filter(Synonyms.synonym.ilike(search_term))
            synonym_results = db.session.execute(q_syn).all()
            if len(synonym_results) == 1:
                substances = synonym_results[0][0].get_row_contents()
            elif len(synonym_results) > 1:
                substances = [r[0].get_row_contents() for r in synonym_results]
                ambiguity = "synonym"
    
    elif search_type == SearchType.InChIKey:
        inchikey_first_block = search_term[:14]
        q = q.filter(Substances.jchem_inchikey.like(inchikey_first_block+"%") | Substances.indigo_inchikey.like(inchikey_first_block+"%"))
        results = [r[0].get_row_contents() for r in db.session.execute(q).all()]
        inchikey_present = any([r["jchem_inchikey"] == search_term for r in results]) or any([r["indigo_inchikey"] == search_term for r in results])
        if inchikey_present and len(results) == 1:
            substances = results[0]
        elif len(results) > 0:
            substances = results
            ambiguity = "inchikey"
    
    elif search_type == SearchType.CASRN:
        q = q.filter(Substances.casrn == search_term)
        results = db.session.execute(q).first()
        if results:
            substances = results[0].get_row_contents()
    
    else:
        raise ValueError("Invalid value for search type")
    
    return jsonify({"ambiguity": ambiguity, "substances": substances})


def get_names_for_dtxsids(dtxsid_list):
    """
    Creates a dictionary that maps a list of DTXSIDs to the EPA-preferred name
    for the substance.
    """
    q = db.select(Substances.preferred_name, Substances.dtxsid).filter(Substances.dtxsid.in_(dtxsid_list))
    results = [c._asdict() for c in db.session.execute(q).all()]
    names_for_dtxsids = {r["dtxsid"]:r["preferred_name"] for r in results}
    return names_for_dtxsids


@app.route("/")
def top_page():
    """
    Landing page.  Doesn't do anything useful, but it's a good check to
    see if the app is running.
    """
    return "<p>Hello, World!</p>"


@app.route("/search/<dtxsid>")
def search_results(dtxsid):
    """
    Endpoint for retrieving search results of a specified DTXSID.

    Parameters
    ----------
    search_term : string
        String used for searching.

    Returns
    -------
    A JSON structure containing a list of records from the database.
    """

    id_query = db.select(Contents.internal_id).filter(Contents.dtxsid == dtxsid)
    internal_ids = [ir.internal_id for ir in db.session.execute(id_query).all()]

    record_query = db.select(
        RecordInfo.source, RecordInfo.internal_id, RecordInfo.link, RecordInfo.record_type, RecordInfo.methodologies,
        RecordInfo.data_type, RecordInfo.description, func.count(Contents.dtxsid)
    ).join_from(
        RecordInfo, Contents, Contents.internal_id==RecordInfo.internal_id
    ).filter(
        RecordInfo.internal_id.in_(internal_ids)
    ).group_by(
        RecordInfo.internal_id
    )
    records = [r._asdict() for r in db.session.execute(record_query)]

    method_number_query = db.select(Methods.internal_id, Methods.method_number).filter(Methods.internal_id.in_(internal_ids))
    method_numbers = [r._asdict() for r in db.session.execute(method_number_query)]
    method_numbers = {mn["internal_id"]: mn["method_number"] for mn in method_numbers}

    for r in records:
        if r["internal_id"] in method_numbers:
            r["method_number"] = method_numbers[r["internal_id"]]

    result_record_types = [r["record_type"] for r in records]
    record_type_counts = Counter(result_record_types)
    for record_type in ["Method", "Fact Sheet", "Spectrum"]:
        if record_type not in record_type_counts:
            record_type_counts[record_type] = 0
    record_type_counts = {k.lower(): v for k,v in record_type_counts.items()}

    return jsonify({"records":records, "record_type_counts":record_type_counts})


@app.route("/get_spectrum/<internal_id>")
def retrieve_spectrum(internal_id):
    """
    Endpoint for retrieving a specified mass spectrum from the database.

    Parameters
    ----------
    internal_id : string
        The unique internal identifier for the spectrum that's being looked for.

    Returns
    -------
    A JSON structure containing the information about the spectrum.
    """
    q = db.select(
            SpectrumData.spectrum, SpectrumData.splash, SpectrumData.normalized_entropy, SpectrumData.spectral_entropy,
            SpectrumData.has_associated_method, SpectrumData.spectrum_metadata
        ).filter(SpectrumData.internal_id==internal_id)
    data_row = db.session.execute(q).first()
    if data_row is not None:
        data_dict = data_row._asdict()

        # Postgres stores the missing values for entropies as 'NaN'; for some reason, passing these
        # to jsonify() causes it to send the dictionary as a string, so fix that
        if len(data_dict["spectrum"]) == 1:
            data_dict["spectral_entropy"] = None
            data_dict["normalized_entropy"] = None
        return jsonify(data_dict)

    else:
        return "Error: invalid internal id."


@app.route("/fact_sheet_list")
def fact_sheet_list():
    """
    Endpoint for retrieving a list of all of the fact sheets present in the
    database.  The current Vue page using this is only displaying the year th
    record was published, hence why the 'year_published' field is being
    generated.

    Parameters
    ----------
    None.

    Returns
    -------
    A list of dictionaries, each one corresponding to one fact sheet in the
    database.
    """

    q = db.select(
        FactSheets.internal_id, FactSheets.fact_sheet_name, FactSheets.analyte, FactSheets.document_type, RecordInfo.source, RecordInfo.link, func.count(Contents.dtxsid)
    ).join_from(
        FactSheets, RecordInfo, FactSheets.internal_id==RecordInfo.internal_id
    ).join_from(
        RecordInfo, Contents, RecordInfo.internal_id==Contents.internal_id, isouter=True
    ).group_by(
        FactSheets.internal_id, RecordInfo.internal_id
    )
    results = [r._asdict() for r in db.session.execute(q).all()]

    single_dtxsid_ids = [r["internal_id"] for r in results if r["count"] == 1]
    q2 = db.select(Contents.internal_id, Contents.dtxsid).filter(Contents.internal_id.in_(single_dtxsid_ids))
    single_dtxsid_results = {r.internal_id: r.dtxsid for r in db.session.execute(q2).all()}

    for i in range(len(results)):
        if results[i]["internal_id"] in single_dtxsid_results:
            results[i]["dtxsid"] = single_dtxsid_results[results[i]["internal_id"]]

    return jsonify({"results":results})


@app.route("/method_list")
def method_list():
    """
    Endpoint for retrieving a list of all of the methods present in the
    database.

    Parameters
    ----------
    None.

    Returns
    -------
    A list of dictionaries, each one corresponding to one method in the
    database.
    """
    
    q = db.select(
        Methods.internal_id, Methods.method_name, Methods.method_number, Methods.date_published, Methods.matrix, Methods.analyte,
        Methods.chemical_class, Methods.pdf_metadata, RecordInfo.source, RecordInfo.methodologies, RecordInfo.description,
        Methods.document_type, Methods.publisher, func.count(Contents.dtxsid)
    ).join_from(
        Methods, RecordInfo, Methods.internal_id==RecordInfo.internal_id
    ).join_from(
        RecordInfo, Contents, RecordInfo.internal_id==Contents.internal_id, isouter=True
    ).group_by(
        Methods.internal_id, RecordInfo.internal_id
    )

    results = [r._asdict() for r in db.session.execute(q).all()]
    results = [{**r, "year_published": util.clean_year(r["date_published"]), "methodology":';'.join(r["methodologies"])} for r in results]
    for r in results:
        if pm := r.get("pdf_metadata"):
            r["author"] = pm.get("Author", None)
            r["limitation"] = pm.get("Limitation", None)
            del r["pdf_metadata"]
        else:
            r["author"] = None
    
    return {"results": results}


@app.route("/get_pdf/<record_type>/<internal_id>")
def get_pdf(record_type, internal_id):
    """
    Retrieve a PDF from the database by the internal ID and type of record.

    Parameters
    ----------
    record_type : string
        A string indicating which kind of record is being retrieved.  Valid
        values are 'fact sheet', 'method', and 'spectrum pdf'.
    
    internal_id : string
        ID of the document in the database.

    Returns
    -------
    The PDF being searched, in the form of an <iframe>-compatible element.
    """
    if record_type.lower() == "fact sheet":
        q = db.select(FactSheets.pdf_data).filter(FactSheets.internal_id==internal_id)
    elif record_type.lower() == "method":
        q = db.select(Methods.pdf_data).filter(Methods.internal_id==internal_id)
    elif record_type.lower() == "spectrum pdf":
        q = db.select(SpectrumPDFs.pdf_data).filter(SpectrumPDFs.internal_id==internal_id)
    else:
        return f"Error: invalid record type {record_type}."
    
    data_row = db.session.execute(q).first()
    if data_row is not None:
        pdf_content = data_row.pdf_data
        response = make_response(pdf_content)
        response.headers['Content-Type'] = "application/pdf"
        response.headers['Content-Disposition'] = f"inline; filename=\"{internal_id}\""
        return response
    else:
        return "Error: PDF name not found."


@app.route("/get_pdf_metadata/<record_type>/<internal_id>")
def get_pdf_metadata(record_type, internal_id):
    """
    Retrieves metadata associated with a PDF.  Both fact sheets and methods have
    associated metadata, so this uses the record_type argument to differentiate
    between them.

    Parameters
    ----------
    record_type : string
        A string indicating which kind of record is being retrieved.  Valid
        values are 'fact sheet' and 'method'.
    
    internal_id : string
        ID of the document in the database.

    Returns
    -------
    A JSON structure containing the metadata, the name, and whether or not the
    method has associated spectra.
    """
    if record_type.lower() == "fact sheet":
        q = db.select(FactSheets.fact_sheet_name.label("doc_name"), FactSheets.pdf_metadata).filter(FactSheets.internal_id==internal_id)
    elif record_type.lower() == "method":
        q = db.select(Methods.method_name.label("doc_name"), Methods.pdf_metadata, Methods.has_associated_spectra).filter(Methods.internal_id==internal_id)
    else:
        return f"Error: invalid record type {record_type}."

    data_row = db.session.execute(q).first()
    if data_row is not None:
        data_row = data_row._asdict()
        return jsonify({
            "pdf_name": data_row["doc_name"],
            "metadata_rows": data_row["pdf_metadata"],
            "has_associated_spectra": data_row.get("has_associated_spectra", False)
        })
    else:
        return "Error: PDF name not found."




@app.route("/find_dtxsids/<internal_id>")
def find_dtxsids(internal_id):
    """
    Returns a list of DTXSIDs associated with the specified internal ID, along
    with additional substance information.  This is mostly used for pulling back
    information on the substances listed in a method or fact sheet.

    Parameters
    ----------
    internal_id : string
        Database ID of the record.

    Returns
    -------
    A JSON structure containing a list of substance information.  This will be
    empty if no records were found.
    """
    q = db.select(Contents.dtxsid).filter(Contents.internal_id==internal_id)
    dtxsids = db.session.execute(q).all()
    if len(dtxsids) > 0:
        dtxsids = [d[0] for d in dtxsids]
        q2 = db.select(Substances.dtxsid, Substances.casrn, Substances.preferred_name).filter(Substances.dtxsid.in_(dtxsids))
        substance_info = db.session.execute(q2).all()
        return jsonify({"substance_list":[c._asdict() for c in substance_info]})
    else:
        print(f"Warning -- no DTXSIDs found for internal ID {internal_id}")
        return jsonify({"substance_list":[]})


@app.route("/substance_similarity_search/<dtxsid>")
def find_similar_substances(dtxsid, similarity_threshold=0.8):
    """
    Makes a call to an EPA-built API for substance similarity and returns the
    list of DTXSIDs of substances with a similarity measure at or above the
    `similarity_threshold` parameter.

    Parameters
    ----------
    dtxsid : string
        The DTXSID to search on.
    
    similarity_threshold : float
        A value from 0 to 1, sent to an EPA API as a threshold for how similar
        the substances you're searching for should be.  Higher values will return
        only highly similar substances.


    Returns
    -------
    A list of similar substances, or None if none were found.
    """

    BASE_URL = "https://ccte-api-ccd.epa.gov/similar-compound/by-dtxsid/"
    response = requests.get(f"{BASE_URL}{dtxsid}/{similarity_threshold}")
    if response.status_code == 200:
        return {"similar_substance_info": response.json()}
    else:
        print("Error: ", response.status_code)
        return {"similar_substance_info": None}


@app.route("/get_similar_methods/<dtxsid>")
def get_similar_methods(dtxsid):
    """
    Searches the database for all methods which contain at least one substance
    of sufficient similarity to the searched substance.  The searched similarity
    level is hardcoded here, and I currently have no plans to make it
    adjustable by the app.

    Parameters
    ----------
    dtxsid : string
        A DTXSID to search on.


    Returns
    -------
    A JSON structure containing information on the related methods.
    """
    similar_substance_info = find_similar_substances(dtxsid, similarity_threshold=0.5)["similar_substance_info"]
    if similar_substance_info is None:
        similar_dtxsids = []
        similarity_dict = {}
    else:
        similar_dtxsids = [ssi["dtxsid"] for ssi in similar_substance_info]
        similarity_dict = {ssi["dtxsid"]: ssi["similarity"] for ssi in similar_substance_info}
    
    # add the actual DTXSID manually
    similar_dtxsids.append(dtxsid)
    similarity_dict[dtxsid] = 1.0001

    q = db.select(
            Contents.internal_id, Contents.dtxsid, RecordInfo.source, RecordInfo.methodologies,
            Methods.method_name, Methods.date_published
        ).filter(
            Contents.dtxsid.in_(similar_dtxsids)
        ).join_from(
            Contents, RecordInfo, Contents.internal_id==RecordInfo.internal_id
        ).join_from(
            Contents, Methods, Contents.internal_id==Methods.internal_id
        )
    results = [c._asdict() for c in db.session.execute(q).all()]

    methods_with_searched_substance = [r["internal_id"] for r in results if r["dtxsid"] == dtxsid]
    dtxsid_names = get_names_for_dtxsids([r["dtxsid"] for r in results])

    # merge info, supply a boolean for whether the searched substance is in the
    # method, and parse the publication year
    results = [{
            **r, "similarity": similarity_dict[r["dtxsid"]], "substance_name":dtxsid_names.get(r["dtxsid"]),
            "has_searched_substance": r["internal_id"] in methods_with_searched_substance,
            "year_published": util.clean_year(r["date_published"]), "methodology": ", ".join(r["methodologies"])
        } for r in results]
    ids_to_method_names = {r["internal_id"]:r["method_name"] for r in results}

    dtxsid_counts = Counter([r["dtxsid"] for r in results])
    dtxsid_counts = [{"dtxsid": k, "num_methods": v, "preferred_name": dtxsid_names.get(k), "similarity": similarity_dict[k]} for k, v in dtxsid_counts.items()]

    return jsonify({"results":results, "ids_to_method_names":ids_to_method_names, "dtxsid_counts":dtxsid_counts})


@app.route("/batch_search", methods=["POST"])
def batch_search():
    """
    Receives a list of DTXSIDs and returns information on all records in the
    database that contain those DTXSIDs.  If a record contains more than one of
    the searched DTXSIDs, then that record will appear once for each searched
    substance it contains.

    The POST should contain a list of DTXSIDs in a corresponding "dtxsids"
    element, but no other parameters are required.
    """
    dtxsid_list = request.get_json()["dtxsids"]
    base_url = request.get_json()["base_url"]
    include_spectrabase = request.get_json()["include_spectrabase"]

    substance_query = db.select(Substances.dtxsid, Substances.casrn, Substances.preferred_name).filter(Substances.dtxsid.in_(dtxsid_list))
    substances = [c._asdict() for c in db.session.execute(substance_query).all()]
    substance_df = pd.DataFrame(substances)

    record_query = db.select(
            Contents.internal_id, Contents.dtxsid, RecordInfo.methodologies, RecordInfo.source, RecordInfo.link, RecordInfo.record_type, RecordInfo.description
        ).filter(Contents.dtxsid.in_(dtxsid_list)).join_from(
            Contents, RecordInfo, Contents.internal_id==RecordInfo.internal_id
        )
    records = [c._asdict() for c in db.session.execute(record_query).all()]
    if not include_spectrabase:
        # don't add as a filter to the query; it'll miss records without sources if it's added there
        records = [r for r in records if r["source"] != "SpectraBase"]
    for i, r in enumerate(records):
        # if a record has no link, have it link back to the search page of the Vue app with the row preselected
        if r["link"] is None:
            records[i]["link"] = f"{base_url}/search/{r['dtxsid']}?initial_row_selected={r['internal_id']}"
    record_df = pd.DataFrame(records)

    result_df = substance_df.merge(record_df, how="right", on="dtxsid")

    result_counts = record_df.groupby(["dtxsid"]).size().reset_index()
    result_counts.columns = ["dtxsid", "num_records"]
    result_counts = pd.DataFrame({"dtxsid":dtxsid_list}).merge(substance_df, how="left", on="dtxsid").merge(result_counts, how="left", on="dtxsid")
    result_counts["num_records"] = result_counts["num_records"].fillna(0)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer) as writer:
        result_counts.to_excel(writer, sheet_name="Substances", index=None)
        result_df.to_excel(writer, sheet_name="Records", index=None)

    headers = {"Content-Disposition": "attachment; filename=batch_search.xlsx", "Content-type":"application/vnd.ms-excel"}

    return Response(buffer.getvalue(), mimetype="application/vnd.ms-excel", headers=headers)


@app.route("/method_with_spectra/<search_type>/<internal_id>")
def method_with_spectra_search(search_type, internal_id):
    """
    Attempts to return information about a method with linked spectra.
    Searching is done using the internal ID of either the method or one of its
    spectra.
    """
    if search_type == "spectrum":
        q = db.select(MethodsWithSpectra.method_id).filter(MethodsWithSpectra.spectrum_id == internal_id)
        result = [c._asdict() for c in db.session.execute(q).all()]
        if len(result) == 0:
            return f"No method found that matches spectrum id '{internal_id}'."
        method_id = result[0]["method_id"]
    elif search_type == "method":
        method_id = internal_id
    else:
        return f"Invalid search type {search_type}."
    
    spectrum_q = db.select(MethodsWithSpectra.spectrum_id).filter(MethodsWithSpectra.method_id == method_id)
    spectrum_list = [c.spectrum_id for c in db.session.execute(spectrum_q).all()]

    info_q = db.select(
            Contents.internal_id, Contents.dtxsid, Substances.preferred_name
        ).filter(
            Contents.internal_id.in_(spectrum_list)
        ).join_from(
            Contents, Substances, Contents.dtxsid==Substances.dtxsid
        )
    info_entries = [c._asdict() for c in db.session.execute(info_q).all()]
    
    return jsonify({"method_id": method_id, "spectrum_ids": spectrum_list, "info": info_entries})


@app.route("/spectrum_count_by_type/", methods=["POST"])
def get_spectrum_count_by_type():
    """
    Endpoint for getting a count of spectrum records that have the specified
    spectrum type as one of its spectrum types.  (A few data sources can have
    multiple spectrum types.)

    Note that parameters are currently handled by a POST rather than in the URL
    (like most of the other functions here) due to the fact that a lot of
    spectrum types have forward slashes in them (e.g., 'LC/MS'), which disrupts
    Flask's routing.

    Currently intended for use with applications outside of the Vue app.
    """

    dtxsid = request.get_json()["dtxsid"]
    spectrum_type = request.get_json()["spectrum_type"]

    q = db.select(Contents.internal_id).filter(
            RecordInfo.methodologies.contains([spectrum_type]) & (RecordInfo.record_type == "Spectrum") & (Contents.dtxsid == dtxsid)
    ).join_from(Contents, RecordInfo, Contents.internal_id==RecordInfo.internal_id)
    return jsonify({"count": len(db.session.execute(q).all())})


@app.route("/substances_for_ids/", methods=["POST"])
def get_substances_for_ids():
    """
    Accepts a list of internal_ids (via POST) and returns a deduplicated list substances
    that appear in those records.
    """

    internal_id_list = request.get_json()["internal_id_list"]

    q = db.select(
            Contents.dtxsid, Substances.preferred_name, Substances.casrn, Substances.jchem_inchikey
        ).filter(Contents.internal_id.in_(internal_id_list)).join_from(Contents, Substances, Contents.dtxsid==Substances.dtxsid).distinct()
    results = [c._asdict() for c in db.session.execute(q).all()]
    result_df = pd.DataFrame(results)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer) as writer:
        result_df.to_excel(writer, sheet_name="Substances", index=None)

    headers = {"Content-Disposition": "attachment; filename=Substances.xlsx", "Content-type":"application/vnd.ms-excel"}

    return Response(buffer.getvalue(), mimetype="application/vnd.ms-excel", headers=headers)


@app.route("/spectrum_similarity_search/", methods=["POST"])
def spectrum_similarity_search():
    """
    Takes a mass range, methodology, and mass spectrum, and returns all spectra
    that match the mass and methodology, with entropy similarities between the
    database spectra and the user-supplied one.
    """
    request_json = request.get_json()
    lower_mass_limit = request_json["lower_mass_limit"]
    upper_mass_limit = request_json["upper_mass_limit"]
    methodology = request.json["methodology"]
    user_spectrum = request.json["spectrum"]

    results = spectrum_search(lower_mass_limit, upper_mass_limit, methodology)

    substance_mapping = {}
    for r in results:
        substance_mapping[r["dtxsid"]] = r["preferred_name"]
        del r["preferred_name"]
        r["similarity"] = spectrum.calculate_entropy_similarity(r["spectrum"], user_spectrum)
    return jsonify({"result_length":len(results), "unique_substances":len(substance_mapping), "results":results, "substance_mapping": substance_mapping})


def spectrum_search(lower_mass_limit, upper_mass_limit, methodology=None):
    """
    Retrieves basic information on a set of spectra from the database,
    constrained by a mass range and an analytical methodology.
    """
    q = db.select(
            Substances.dtxsid, Substances.preferred_name, Contents.internal_id, RecordInfo.description, SpectrumData.spectrum, SpectrumData.spectrum_metadata
        ).filter(
            Substances.monoisotopic_mass.between(lower_mass_limit, upper_mass_limit) & (RecordInfo.data_type=="Spectrum")
        ).join_from(
            Substances, Contents, Substances.dtxsid == Contents.dtxsid
        ).join_from(
            Contents, RecordInfo, Contents.internal_id==RecordInfo.internal_id
        ).join_from(
            Contents, SpectrumData, Contents.internal_id==SpectrumData.internal_id
        )
    if methodology:
        q = q.filter(RecordInfo.methodologies.any(methodology))
    results = [c._asdict() for c in db.session.execute(q).all()]
    return results


@app.route("/spectral_entropy/", methods=["POST"])
def spectral_entropy():
    """
    Calculates the spectral entropy for a single spectrum.
    """
    entropy = spectrum.calculate_spectral_entropy(request.get_json()["spectrum"])
    return jsonify({"entropy": entropy})


@app.route("/entropy_similarity/", methods=["POST"])
def entropy_similarity():
    """
    Calculates the entropy similarity for two spectra.
    """
    post_data = request.get_json()
    similarity = spectrum.calculate_entropy_similarity(post_data["spectrum_1"], post_data["spectrum_2"])
    return jsonify({"similarity": similarity})


@app.route("/record_counts_by_dtxsid/", methods=["POST"])
def get_record_counts_by_dtxsid():
    """
    Takes a list of DTXSIDs as the POST argument, and for each DTXSID, it
    returns a dictionary containing the counts of record types that are present
    in the database.
    """
    dtxsid_list = request.get_json()["dtxsids"]
    q = db.select(Contents.dtxsid, RecordInfo.record_type, func.count(RecordInfo.internal_id)).join_from(Contents, RecordInfo, Contents.internal_id==RecordInfo.internal_id).filter(Contents.dtxsid.in_(dtxsid_list)).group_by(Contents.dtxsid, RecordInfo.record_type)
    results = [c._asdict() for c in db.session.execute(q).all()]
    result_dict = defaultdict(dict)
    for r in results:
        result_dict[r["dtxsid"]].update({r["record_type"]: r["count"]})
    return jsonify(result_dict)


@app.route("/max_similarity_by_dtxsid/", methods=["POST"])
def max_similarity_by_dtxsid():
    """
    This endpoint allows a user to submit a list of DTXSIDs and a spectrum.  In
    response, the user will get back the DTXSIDs mapped to similarity scores.
    The scores will be the highest similarity score computed on the user-
    supplied spectrum and all spectra in this database for that DTXSID.  If no
    spectra were found, the DTXSID will map to None.
    
    This access point is intended to be used by CFMID.
    """
    request_json = request.get_json()
    dtxsids = request_json["dtxsids"]
    if type(dtxsids) == str:
        dtxsids = [dtxsids]
    user_spectrum = request_json["spectrum"]

    da = request_json.get("da_window")
    ppm = request_json.get("ppm_window")

    results = get_spectra_for_substances(dtxsids)

    substance_dict = {d:None for d in dtxsids}
    for r in results:
        similarity = spectrum.calculate_entropy_similarity(user_spectrum, r["spectrum"], da_error=da, ppm_error=ppm)
        if substance_dict[r["dtxsid"]] is None or substance_dict[r["dtxsid"]] < similarity:
            substance_dict[r["dtxsid"]] = similarity

    return jsonify({"results":substance_dict})


@app.route("/all_similarities_by_dtxsid/", methods=["POST"])
def all_similarities_by_dtxsid():
    request_json = request.get_json()
    dtxsids = request_json["dtxsids"]
    if type(dtxsids) == str:
        dtxsids = [dtxsids]
    user_spectrum = request_json["spectrum"]

    da = request_json.get("da_window")
    ppm = request_json.get("ppm_window")
    min_intensity = request_json.get("min_intensity", 0)

    results = get_spectra_for_substances(dtxsids, [SpectrumData.spectrum_metadata])

    # mass query
    q = db.select(Substances.dtxsid, Substances.monoisotopic_mass).filter(Substances.dtxsid.in_(dtxsids))
    mass_results = [c._asdict() for c in db.session.execute(q).all()]

    substance_dict = {d:[] for d in dtxsids}
    mass_dict = {mr["dtxsid"]: mr["monoisotopic_mass"] for mr in mass_results}
    for r in results:
        result_spectrum = [[mz, i] for mz, i in r["spectrum"] if (mz < (mass_dict[r["dtxsid"]]-1.5)) and (i > min_intensity)]
        if len(result_spectrum) == 0:
            continue
        if r["description"].startswith("#"):
            description = None
        else:
            description = ";".join(r["description"].split(";")[:-1])
        combined_spectrum = spectrum.combine_peaks(result_spectrum)
        spectral_entropy = spectrum.calculate_spectral_entropy(combined_spectrum)
        normalized_entropy = spectral_entropy/len(combined_spectrum)
        information = {"Points": len(result_spectrum), "Spectral Entropy": spectral_entropy, "Normalized Entropy": normalized_entropy,
                       "Rating": "Clean" if spectral_entropy <= 3.0 and normalized_entropy <= 0.8 else "Noisy"}
        entropy_similarity = spectrum.calculate_entropy_similarity(user_spectrum, combined_spectrum, da_error=da, ppm_error=ppm)
        cosine_similarity = spectrum.cosine_similarity(user_spectrum, combined_spectrum)
        substance_dict[r["dtxsid"]].append({"entropy_similarity": entropy_similarity, "cosine_similarity": cosine_similarity, "description": description, "metadata": r["spectrum_metadata"], "information": information})

    return jsonify({"results":substance_dict})


def get_spectra_for_substances(dtxsid_list, additional_fields=[]):
    """
    Takes a list of DTXSIDs and returns all spectra associated with those DTXSIDs.
    """
    q = db.select(Contents.dtxsid, RecordInfo.internal_id, RecordInfo.description, SpectrumData.spectrum, *additional_fields).filter(
        (Contents.dtxsid.in_(dtxsid_list)) & (RecordInfo.data_type == "Spectrum")
    ).join_from(
        Contents, RecordInfo, Contents.internal_id==RecordInfo.internal_id
    ).join_from(
        Contents, SpectrumData, Contents.internal_id==SpectrumData.internal_id
    )
    return [c._asdict() for c in db.session.execute(q).all()]


@app.route("/get_info_by_id/<internal_id>")
def get_info_by_id(internal_id):
    q = db.select(RecordInfo).filter(RecordInfo.internal_id == internal_id)
    result = db.session.execute(q).first()
    if result:
        return jsonify({"result": result[0].get_row_contents()})
    else:
        return jsonify({"result": None})


@app.route("/database_summary/")
def database_summary():
    q_types = db.select(RecordInfo.record_type, RecordInfo.data_type, func.count(RecordInfo.internal_id)).group_by(RecordInfo.record_type, RecordInfo.data_type)
    type_dict = defaultdict(dict)
    for r in db.session.execute(q_types).all():
        r = r._asdict()
        type_dict[r["record_type"]][r["data_type"] if r["data_type"] else "None"] = r["count"]

    q_sources = db.select(func.count(func.distinct(RecordInfo.source)))
    unique_sources = db.session.execute(q_sources).all()[0][0]

    q_substances = db.select(func.count(func.distinct(Contents.dtxsid)))
    unique_substances = db.session.execute(q_substances).all()[0][0]
    return jsonify({"result":"success", "substances_appearing": unique_substances, "source_count": unique_sources, "result_types": type_dict})


@app.route("/spectra_for_substances/", methods=["POST"])
def spectra_for_substances():
    dtxsids = request.get_json()["dtxsids"]
    spectrum_results = get_spectra_for_substances(dtxsids)
    names_for_dtxsids = get_names_for_dtxsids(dtxsids)
    return jsonify({"spectra":spectrum_results, "substance_mapping": names_for_dtxsids})


@app.route("/get_image_for_dtxsid/<dtxsid>")
def get_image_for_dtxsid(dtxsid):
    """
    Retrieves a substance's image from the database.
    """
    q = db.select(SubstanceImages.png_image).filter(SubstanceImages.dtxsid==dtxsid)
    result = db.session.execute(q).first()
    if result is not None:
        image = result.png_image
        response = make_response(image)
        response.headers['Content-Type'] = "image/png"
        response.headers['Content-Disposition'] = f"inline; filename=\"{dtxsid}\".png"
        return response
    else:
        return Response(status=204)


@app.route("/substring_search/<substring>")
def substring_search(substring):
    preferred_name_query = db.select(
            Substances.preferred_name, Substances.dtxsid, Substances.casrn, Substances.monoisotopic_mass, Substances.molecular_formula
        ).filter(Substances.preferred_name.ilike(f"%{substring}%"))
    synonym_query = db.select(
            Synonyms.synonym, Synonyms.dtxsid, Substances.preferred_name, Substances.casrn, Substances.monoisotopic_mass, Substances.molecular_formula
        ).join_from(
            Synonyms, Substances, Synonyms.dtxsid==Substances.dtxsid
        ).filter(Synonyms.synonym.ilike(f"%{substring}%"))
    preferred_names = [r._asdict() for r in db.session.execute(preferred_name_query).all()]
    synonyms = [r._asdict() for r in db.session.execute(synonym_query).all()]

    info_dict = {}
    for pn in preferred_names:
        info_dict[pn["dtxsid"]] = {"synonyms": [], **pn}
    for s in synonyms:
        if s["dtxsid"] in info_dict:
            info_dict[s["dtxsid"]]["synonyms"].append(s["synonym"])
        else:
            info_dict[s["dtxsid"]] = {**s, "synonyms": [s["synonym"]]}
            del info_dict[s["dtxsid"]]["synonym"]
    info_list = [v for _,v in info_dict.items()]
    return jsonify({"info_list": info_list})


@app.route("/get_ms_ready_methods/<inchikey>")
def get_ms_ready_methods(inchikey):
    first_block = inchikey.split("-")[0]
    q = db.select(
            RecordInfo.source, RecordInfo.internal_id, RecordInfo.link, RecordInfo.record_type, RecordInfo.methodologies,
            RecordInfo.data_type, RecordInfo.description, func.count(Contents.dtxsid)
        ).filter(
            Substances.jchem_inchikey.like(first_block+"%") & (Substances.jchem_inchikey != inchikey)
        ).join_from(
            Contents, Substances, Contents.dtxsid == Substances.dtxsid
        ).join_from(
            Contents, RecordInfo, Contents.internal_id == RecordInfo.internal_id
        ).group_by(
            RecordInfo.internal_id
        )
    results = [c._asdict() for c in db.session.execute(q).all()]

    internal_ids = [c["internal_id"] for c in results]
    method_number_query = db.select(Methods.internal_id, Methods.method_number).filter(Methods.internal_id.in_(internal_ids))
    method_numbers = [r._asdict() for r in db.session.execute(method_number_query)]
    method_numbers = {mn["internal_id"]: mn["method_number"] for mn in method_numbers}

    for r in results:
        if r["internal_id"] in method_numbers:
            r["method_number"] = method_numbers[r["internal_id"]]
    
    return jsonify({"length": len(results), "results": results})


@app.route("/get_substance_file_for_record/<internal_id>")
def get_substance_file_for_record(internal_id):
    """
    Creates an Excel workbook listing the substances in the specified
    record.
    """
    substance_list = find_dtxsids(internal_id).json["substance_list"]
    substance_list = [(sl["dtxsid"], sl["casrn"], sl["preferred_name"]) for sl in substance_list]
    substance_df = pd.DataFrame(substance_list, columns=["DTXSID", "CASRN", "Preferred Name"])

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer) as writer:
        substance_df.to_excel(writer, sheet_name="Substances", index=None)

    headers = {"Content-Disposition": "attachment; filename=substances.xlsx", "Content-type":"application/vnd.ms-excel"}

    return Response(buffer.getvalue(), mimetype="application/vnd.ms-excel", headers=headers)



if __name__ == "__main__":
    db.init_app(app)
    app.run(host='0.0.0.0', port=5000)
