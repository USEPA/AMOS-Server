from collections import Counter
import configparser
import csv
from enum import Enum
import io
import json
import re

from flask import Flask, jsonify, make_response, request
from flask_cors import CORS
import requests

from table_definitions import db, Compounds, Contents, Methods, Monographs, \
    MethodsWithSpectra, RecordInfo, SpectrumData, SpectrumPDFs, Synonyms

# load info for PostgreSQL access from external file
config = configparser.ConfigParser()
config.read("vars.ini")
uname = config["POSTGRES_ACCESS"]["username"]
pwd = config["POSTGRES_ACCESS"]["password"]

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = f"postgresql+psycopg2://{uname}:{pwd}@v2626umcth819.rtord.epa.gov:5435/greg"

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = "secretkey"

CORS(app, resources={r'/*': {'origins': '*'}})



class SearchType(Enum):
    InChIKey = 1
    CASRN = 2
    CompoundName = 3
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
        return SearchType.CompoundName


def get_dtxsid_for_search_term(search_term):
    """
    Takes a string containing a search term, and tries to find a DTXSID that
    matches it.  There are four cases, depending on what the search term looks
    like:

    - If it's a DTXSID already, check to see if it exists in the database; if it
    is there, return it.
    - If it's a CASRN, check if something in the Compounds table has that CASRN,
    and return the corresponding DTXSID if it is.
    - If it's an InChIKey, check if something in the Compounds table has that
    InChIKey, and return the corresponding DTXSID if it is.
    - If it's a compound name, check if something in the Compounds table has
    that name.  If not, see if the name appears in the Synonyms table.  If
    either of those has a match, return the correpsonding DTXSID.

    If no DTXSID is found, the function returns None.

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
    dtxsid = None   # default value

    if search_type == SearchType.DTXSID:
        q = db.select(Compounds.dtxsid).filter(Compounds.dtxsid == search_term)
        results = db.session.execute(q).all()
        if len(results) > 0:
            dtxsid = search_term
    elif search_type == SearchType.CompoundName:
        q = db.select(Compounds.dtxsid).filter(Compounds.preferred_name.ilike(search_term))
        results = db.session.execute(q).all()
        # if no matches, check if it's a synonym
        if len(results) == 0:
            q_syn = db.select(Synonyms.dtxsid).filter(Synonyms.synonym.ilike(search_term))
            synonym_results = db.session.execute(q_syn).all()
            if len(synonym_results) > 0:
                dtxsid = synonym_results[0].dtxsid
        else:
            dtxsid = results[0].dtxsid
    else: 
        if search_type == SearchType.InChIKey:
            q = db.select(Compounds.dtxsid).filter(Compounds.jchem_inchikey == search_term)
        elif search_type == SearchType.CASRN:
            q = db.select(Compounds.dtxsid).filter(Compounds.casrn == search_term)
        else:
            raise ValueError("Invalid value for search type")
        results = db.session.execute(q).all()
        if len(results) > 0:
            dtxsid = results[0].dtxsid

    return dtxsid


def get_names_for_dtxsids(dtxsid_list):
    """
    Creates a dictionary that maps a list of DTXSIDs to the EPA-preferred name
    for the compound.
    """
    q = db.select(Compounds.preferred_name, Compounds.dtxsid).filter(Compounds.dtxsid.in_(dtxsid_list))
    results = [c._asdict() for c in db.session.execute(q).all()]
    names_for_dtxsids = {r["dtxsid"]:r["preferred_name"] for r in results}
    return names_for_dtxsids


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
    elif re.match("^[0-9]+/[0-9]{4}$", year_value):
        return int(year_value[-4:])
    else:
        print(f"Issue with year value {year_value} -- unclear string format")
        return year_value


@app.route("/")
def top_page():
    """
    Landing page.  Doesn't do anything useful, but it's a good check to
    see if the app is running.
    """
    return "<p>Hello, World!</p>"


@app.route("/search/<search_term>")
def search_results(search_term):
    """
    Endpoint for retrieving search results of a specified compound.

    Parameters
    ----------
    search_term : string
        String used for searching.

    Returns
    -------
    A JSON structure containing a list of records from the database, as well as
    general information on the searched compound.
    """
    dtxsid = get_dtxsid_for_search_term(search_term)
    if dtxsid is None:
        return jsonify({"no_compound_match": True})

    # get_dtxsid_for_search_term should catch invalid DTXSIDs, so compound_info
    # shouldn't need to be checked if it's empty
    info_query = db.select(Compounds).filter(Compounds.dtxsid == dtxsid)
    info_results = db.session.execute(info_query).all()
    compound_info = info_results[0][0].get_row_contents()

    id_query = db.select(Contents.internal_id).filter(Contents.dtxsid == dtxsid)
    internal_ids = [ir.internal_id for ir in db.session.execute(id_query).all()]
    record_query = db.select(RecordInfo.source, RecordInfo.internal_id, RecordInfo.link, RecordInfo.record_type, RecordInfo.spectrum_types,
                       RecordInfo.data_type, RecordInfo.description).filter(RecordInfo.internal_id.in_(internal_ids))
    records = [r._asdict() for r in db.session.execute(record_query)]

    result_record_types = [r["record_type"] for r in records]
    record_type_counts = Counter(result_record_types)
    for record_type in ["Method", "Monograph", "Spectrum"]:
        if record_type not in record_type_counts:
            record_type_counts[record_type] = 0
    record_type_counts = {k.lower(): v for k,v in record_type_counts.items()}

    return jsonify({"records":records, "compound_info":compound_info, "record_type_counts":record_type_counts})


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
    A JSON structure containing the information about the spectrum - entropies,
    SPLASH, and the spectrum itself.
    """
    q = db.select(SpectrumData.spectrum, SpectrumData.splash, SpectrumData.normalized_entropy, SpectrumData.spectral_entropy, SpectrumData.has_associated_method).filter(SpectrumData.internal_id==internal_id)
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


@app.route("/monograph_list")
def monograph_list():
    """
    Endpoint for retrieving a list of all of the monographs present in the
    database.  The current Vue page using this is only displaying the year th
    record was published, hence why the 'year_published' field is being
    generated.

    Parameters
    ----------
    None.

    Returns
    -------
    A list of dictionaries, each one corresponding to one monograph record in
    the database.
    """
    q = db.select(Monographs.internal_id, Monographs.monograph_name, Monographs.date_published, Monographs.sub_source)
    results = [r._asdict() for r in db.session.execute(q).all()]
    results = [{**r, "year_published": clean_year(r["date_published"])} for r in results]
    return jsonify({"results":results})


@app.route("/method_list")
def method_list():
    """
    Endpoint for retrieving a list of all of the methods present in the
    database.  The current Vue page using this is only displaying the year th
    record was published, hence why the 'year_published' field is being
    generated.  Similarly, the 'methodology' field is just a concatenation of
    the spectrum types corresponding to the record.

    Parameters
    ----------
    None.

    Returns
    -------
    A list of dictionaries, each one corresponding to one method in the
    database.
    """
    q = db.select(Methods.internal_id, Methods.method_name, Methods.method_number, Methods.date_published,
                  Methods.matrix, Methods.analyte, RecordInfo.source, RecordInfo.spectrum_types,
                  RecordInfo.description).join_from(Methods, RecordInfo, Methods.internal_id==RecordInfo.internal_id)
    results = [r._asdict() for r in db.session.execute(q).all()]
    results = [{**r, "year_published":clean_year(r["date_published"]), "methodology":';'.join(r["spectrum_types"])} for r in results]
    return jsonify({"results": results})


@app.route("/get_pdf/<record_type>/<internal_id>")
def get_pdf(record_type, internal_id):
    """
    Retrieve a PDF from the database by the internal ID.  There are three
    different tables that house PDFs -- one for methods, one for monographs, and
    one for spectra stored as PDFs.  They are differentiated by the record_type
    argument.
    """
    if record_type.lower() == "monograph":
        q = db.select(Monographs.pdf_data).filter(Monographs.internal_id==internal_id)
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
    Retrieves metadata associated with a PDF.  Both monographs and methods have
    associated metadata, so this uses the record_type argument to differentiate
    between them.

    Parameters
    ----------
    record_type : string
        A string indicating which kind of record is being retrieved.  Valid
        values are 'monograph' and 'method'.
    
    internal_id : string
        ID of the document in the database.

    Returns
    -------
    A JSON structure containing the metadata, the name, and whether or not the
    method has associated spectra.
    """
    if record_type.lower() == "monograph":
        q = db.select(Monographs.monograph_name.label("doc_name"), Monographs.pdf_metadata).filter(Monographs.internal_id==internal_id)
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
        print("Error")
        return "Error: PDF name not found."


@app.route("/find_inchikeys/<inchikey>")
def find_inchikeys(inchikey):
    """
    Locates and returns all InChIKeys whose first block matches the specified
    key.  Searches of the database by InChIKey may be looking for a variant of
    the compound instead of what they searched for, and another compound with a
    different InChIKey may cover it.

    Parameters
    ----------
    inchikey : string
        The InChIKey being searched on.

    Returns
    -------
    A JSON structure containing an indicator of whether the searched InChIKey
    exists, as well as a list of all InChIKeys with the same first block.
    """
    inchikey_first_block = inchikey[:14]
    q = db.select(Compounds.jchem_inchikey, Compounds.preferred_name).filter(Compounds.jchem_inchikey.like(inchikey_first_block+"%"))
    results = [r._asdict() for r in db.session.execute(q).all()]
    inchikeys = [r["jchem_inchikey"] for r in results]
    inchikey_present = inchikey in inchikeys
    return jsonify({
        "inchikey_present": inchikey_present,
        "unique_inchikeys": sorted(results, key = lambda x: x["jchem_inchikey"])
    })


@app.route("/find_dtxsids/<internal_id>")
def find_dtxsids(internal_id):
    """
    Returns a list of DTXSIDs associated with the specified internal ID, along
    with additional compound information.  This is mostly used for pulling back
    information on the compounds listed in a method or monograph.

    Parameters
    ----------
    internal_id : string
        Database ID of the record.

    Returns
    -------
    A JSON structure containing a list of compound information.  This will be
    empty if no records were found.
    """
    q = db.select(Contents.dtxsid).filter(Contents.internal_id==internal_id)
    dtxsids = db.session.execute(q).all()
    if len(dtxsids) > 0:
        dtxsids = [d[0] for d in dtxsids]
        q2 = db.select(Compounds.dtxsid, Compounds.casrn, Compounds.preferred_name).filter(Compounds.dtxsid.in_(dtxsids))
        compound_info = db.session.execute(q2).all()
        return jsonify({"compound_list":[c._asdict() for c in compound_info]})
    else:
        print(f"Warning -- no DTXSIDs found for internal ID {internal_id}")
        return jsonify({"compound_list":[]})


@app.route("/compound_similarity_search/<search_term>")
def find_similar_compounds(search_term, similarity_threshold=0.8):
    """
    Makes a call to an EPA-built API for compound similarity and returns the
    list of DTXSIDs of compounds with a similarity measure at or above the
    `similarity_threshold` parameter.

    Parameters
    ----------
    search_term : string
        A name, CASRN, InChIKey, or DTXSID to search on.
    
    similarity_threshold : float
        A value from 0 to 1, sent to an EPA API as a threshold for how similar
        the compounds you're searching for should be.  Higher values will return
        only highly similar compounds.


    Returns
    -------
    A JSON structure containing a list of compound information.  This will be
    empty if no records were found.
    """
    dtxsid = get_dtxsid_for_search_term(search_term)

    if dtxsid is None:
        return None, {"response": False}
    
    BASE_URL = "https://ccte-api-ccd-dev.epa.gov/similar-compound/by-dtxsid/"
    response = requests.get(f"{BASE_URL}{dtxsid}/{similarity_threshold}")
    if response.status_code == 200:
        return dtxsid, response.json()
    else:
        print("Error: ", response.status_code)
        return None, {"response": False}


@app.route("/get_similar_methods/<search_term>")
def get_similar_methods(search_term):
    """
    Searches the database for all methods which contain at least one compound
    of sufficient similarity to the searched compound.  The searched similarity
    level is hardcoded here, and I currently have no plans to make it
    adjustable by the app.
    """
    dtxsid, similar_compounds_json = find_similar_compounds(search_term, similarity_threshold=0.5)
    similar_dtxsids = [sc["dtxsid"] for sc in similar_compounds_json]
    similarity_dict = {sc["dtxsid"]: sc["similarity"] for sc in similar_compounds_json}

    # add the actual DTXSID manually -- the case where there are methods for the DTXSID will likely be changed down the road
    similar_dtxsids.append(dtxsid)
    similarity_dict[dtxsid] = 1

    q = db.select(
            Contents.internal_id, Contents.dtxsid, RecordInfo.source, RecordInfo.spectrum_types,
            Methods.method_name, Methods.date_published
        ).filter(Contents.dtxsid.in_(similar_dtxsids)).join_from(Contents, RecordInfo, Contents.internal_id==RecordInfo.internal_id).join_from(Contents, Methods, Contents.internal_id==Methods.internal_id)
    results = [c._asdict() for c in db.session.execute(q).all()]

    methods_with_searched_compound = [r["internal_id"] for r in results if r["dtxsid"] == dtxsid]
    dtxsid_names = get_names_for_dtxsids([r["dtxsid"] for r in results])

    # merge info, supply a boolean for whether the searched compound is in the
    # method, and parse the publication year
    results = [{
            **r, "similarity": similarity_dict[r["dtxsid"]], "compound_name":dtxsid_names.get(r["dtxsid"]),
            "has_searched_compound": r["internal_id"] in methods_with_searched_compound,
            "year_published": clean_year(r["date_published"])
        } for r in results]
    ids_to_method_names = {r["internal_id"]:r["method_name"] for r in results}

    return jsonify({"results":results, "ids_to_method_names":ids_to_method_names})


@app.route("/batch_search", methods=["POST"])
def batch_search():
    """
    Receives a list of DTXSIDs and returns information on all records in the
    database that contain those DTXSIDs.  If a record contains more than one of
    the searched DTXSIDs, then that record will appear once for each searched
    compound it contains.
    """
    dtxsid_list = request.get_json()["dtxsids"]
    q = db.select(
            Contents.internal_id, Contents.dtxsid, RecordInfo.spectrum_types, RecordInfo.source, RecordInfo.link,
            RecordInfo.record_type, RecordInfo.description
        ).filter(Contents.dtxsid.in_(dtxsid_list)).join_from(Contents, RecordInfo, Contents.internal_id==RecordInfo.internal_id)
    results = [c._asdict() for c in db.session.execute(q).all()]

    if len(results) > 0:
        base_url = request.get_json()["base_url"]
        for i, r in enumerate(results):
            # if a record has no link, have it link back to the search page of the Vue app with the row preselected
            if r["link"] is None:
                results[i]["link"] = f"{base_url}/search/{r['dtxsid']}?initial_row_selected={r['internal_id']}"

        # construct the CSV as a string
        f = io.StringIO("")
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

        return jsonify({"csv_string":f.getvalue()})
    else:
        return jsonify({"csv_string":""})


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

    info_q = db.select(Contents.internal_id, Contents.dtxsid, Compounds.preferred_name).filter(Contents.internal_id.in_(spectrum_list)).join_from(Contents, Compounds, Contents.dtxsid==Compounds.dtxsid)
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
            RecordInfo.spectrum_types.contains([spectrum_type]) & (RecordInfo.record_type == "Spectrum") & (Contents.dtxsid == dtxsid)
    ).join_from(Contents, RecordInfo, Contents.internal_id==RecordInfo.internal_id)
    return jsonify({"count": len(db.session.execute(q).all())})



if __name__ == "__main__":
    db.init_app(app)
    app.run(host='0.0.0.0', port=5000)