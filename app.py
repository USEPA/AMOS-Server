import logging
import os
import re
import ssl
from collections import Counter
from enum import Enum

import pandas as pd
import requests
import sentry_sdk
import urllib3
from flask import Flask, jsonify, make_response, request, Response
from flask_cors import CORS
from flask_swagger import swagger
from flask_swagger_ui import get_swaggerui_blueprint
from sentry_sdk.integrations.flask import FlaskIntegration
from sqlalchemy import func, or_

import common_queries as cq
import spectrum
import util
from table_definitions import db, AnalyticalQC, ClassyFire, Contents, DataSourceInfo, FactSheets, \
    FunctionalUseClasses, InfraredSpectra, MassSpectra, Methods, MethodsWithSpectra, NMRSpectra, \
    RecordInfo, SubstanceImages, Substances, Synonyms


class CustomHttpAdapter(requests.adapters.HTTPAdapter):
    # "Transport adapter" that allows us to use custom ssl_context.

    def __init__(self, ssl_context=None, **kwargs):
        self.ssl_context = ssl_context
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False):
        self.poolmanager = urllib3.poolmanager.PoolManager(
            num_pools=connections, maxsize=maxsize,
            block=block, ssl_context=self.ssl_context)


def get_legacy_session():
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
    session = requests.session()
    session.mount('https://', CustomHttpAdapter(ctx))
    return session


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

# Load connection info for PostgreSQL & API access
ccte_api_server = os.environ['CCTE_API_SERVER']
ccte_api_key = os.environ['CCTE_API_KEY']

app = Flask(__name__)


@app.get('/api/amos/swagger.json')
def get_swagger():
    swag = swagger(app)
    swag['info']['version'] = "1.0"
    swag['info']['title'] = "AMOS API"
    return jsonify(swag)


# Swagger UI route
SWAGGER_URL = '/api/amos/swagger'
API_URL = '/api/amos/swagger.json'
swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "AMOS API"
    }
)

app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

if os.environ.get('SQLALCHEMY_DATABASE_URI', None):
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get('SQLALCHEMY_DATABASE_URI')
else:
    uname = os.environ.get('AMOS_POSTGRES_USER', None)
    pwd = os.environ.get('AMOS_POSTGRES_PASSWORD', None)
    server = os.environ.get('AMOS_POSTGRES_SERVER', 'localhost')
    port = os.environ.get('AMOS_POSTGRES_PORT', '5432')
    database = os.environ.get('AMOS_POSTGRES_DATABASE', 'amos')
    app.config["SQLALCHEMY_DATABASE_URI"] = f"postgresql+psycopg2://{uname}:{pwd}@{server}:{port}/{database}"

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = "secretkey"



CORS(app, resources={r'/*': {'origins': '*'}})


# TODO (2025-03-07): If paginated endpoints for the methods and fact sheets are working after a
# month without complaints, delete the old endpoints.


class SearchType(Enum):
    InChIKey = 1
    CASRN = 2
    SubstanceName = 3
    DTXSID = 4


def determine_search_type(search_term):
    """
    Determine whether the search term in question is an InChIKey, CAS number, or a name.
    --
    search_term : string
        String used for searching.

    Returns
    --
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


@app.get("/api/amos/get_substances_for_search_term/<search_term>")
def get_substances_for_search_term(search_term):
    """
    Returns substances by a search term.

    Takes a string containing a search term, and tries to find any DTXSIDs that
    match it, returning them along with information about the substances.

    If no DTXSID is found, the function returns None.  If multiple synonyms or
    the first blocks of multiple InChIKeys are matched, the ambiguity variable
    will be passed indicating the issue, along with a list of the substances
    and information about them.

    ---
    parameters:
      - in: path
        name: search_term
        type: string
    responses:
      200:
        description: Operation successful
    """
    search_type = determine_search_type(search_term)
    substances = None  # default value
    ambiguity = None  # default value
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
            q_syn = q.join_from(Synonyms, Substances, Synonyms.dtxsid == Substances.dtxsid).filter(
                Synonyms.synonym.ilike(search_term))
            synonym_results = db.session.execute(q_syn).all()
            if len(synonym_results) == 1:
                substances = synonym_results[0][0].get_row_contents()
            elif len(synonym_results) > 1:
                substances = [r[0].get_row_contents() for r in synonym_results]
                ambiguity = "synonym"

    elif search_type == SearchType.InChIKey:
        results = cq.inchikey_first_block_search(search_term[:14])
        """ inchikey_first_block = search_term[:14]
        q = q.filter(Substances.jchem_inchikey.like(inchikey_first_block+"%") | Substances.indigo_inchikey.like(inchikey_first_block+"%"))
        results = [r[0].get_row_contents() for r in db.session.execute(q).all()] """
        inchikey_present = any([r["jchem_inchikey"] == search_term for r in results]) or any(
            [r["indigo_inchikey"] == search_term for r in results])
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


@app.get("/api/amos/search/<dtxsid>")
def search_results(dtxsid):
    """
    Endpoint for retrieving search results of a specified DTXSID.

    Parameters
    ---
    parameters:
      - in: path
        name: stxsid
        type: string
    responses:
      200:
        description: A JSON structure containing a list of records from the database.
    """

    id_query = db.select(Contents.internal_id).filter(Contents.dtxsid == dtxsid)
    internal_ids = [ir.internal_id for ir in db.session.execute(id_query).all()]

    record_query = db.select(
        RecordInfo.source, RecordInfo.internal_id, RecordInfo.link, RecordInfo.record_type, RecordInfo.methodologies,
        RecordInfo.data_type, RecordInfo.description, func.count(Contents.dtxsid)
    ).join_from(
        RecordInfo, Contents, Contents.internal_id == RecordInfo.internal_id
    ).filter(
        RecordInfo.internal_id.in_(internal_ids)
    ).group_by(
        RecordInfo.internal_id
    )
    records = [r._asdict() for r in db.session.execute(record_query)]

    # add method numbers to methods found in the search
    method_number_query = db.select(Methods.internal_id, Methods.method_number, Methods.document_type).filter(
        Methods.internal_id.in_(internal_ids))
    method_info = [r._asdict() for r in db.session.execute(method_number_query)]
    method_info = {mn["internal_id"]: {"method_number": mn["method_number"], "document_type": mn["document_type"]} for
                   mn in method_info}

    # add mass spectrum entropies to data
    spectrum_data_query = db.select(MassSpectra.internal_id, MassSpectra.spectral_entropy,
                                    MassSpectra.normalized_entropy).filter(MassSpectra.internal_id.in_(internal_ids))
    spectrum_info = [r._asdict() for r in db.session.execute(spectrum_data_query)]
    spectrum_info = {
        si["internal_id"]: {"spectral_entropy": si["spectral_entropy"], "normalized_entropy": si["normalized_entropy"]}
        for si in spectrum_info}

    for r in records:
        if r["internal_id"] in method_info:
            r["method_number"] = method_info[r["internal_id"]]["method_number"]
            r["method_type"] = method_info[r["internal_id"]]["document_type"]
        if r["record_type"] == "Spectrum":
            if r["internal_id"] in spectrum_info:
                r["spectrum_rating"] = spectrum.spectrum_rating(
                    spectrum_info[r["internal_id"]]["spectral_entropy"],
                    spectrum_info[r["internal_id"]]["normalized_entropy"]
                )
            else:
                r["spectrum_rating"] = "N/A"

    # Fill in missing record types with zeroes
    result_record_types = [r["record_type"] for r in records]
    record_type_counts = Counter(result_record_types)
    for record_type in ["Method", "Fact Sheet", "Spectrum"]:
        if record_type not in record_type_counts:
            record_type_counts[record_type] = 0
    record_type_counts = {k.lower(): v for k, v in record_type_counts.items()}

    return jsonify({"records": records, "record_type_counts": record_type_counts})


@app.get("/api/amos/get_mass_spectrum/<internal_id>")
def retrieve_mass_spectrum(internal_id):
    """
    Endpoint for retrieving a specified mass spectrum from the database.

    ---
    parameters:
      - in: path
        name: internal_id
        type: integer
        description: The unique internal identifier for the spectrum that's being looked for.
    responses:
      200:
        description: A JSON structure containing the information about the spectrum.
    """
    q = db.select(
        MassSpectra.spectrum, MassSpectra.splash, MassSpectra.normalized_entropy, MassSpectra.spectral_entropy,
        MassSpectra.has_associated_method, MassSpectra.spectrum_metadata
    ).filter(MassSpectra.internal_id == internal_id)
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


@app.get("/api/amos/fact_sheet_list")
def fact_sheet_list():
    """
    Endpoint for retrieving a list of all the fact sheets present in the database.

    The current Vue page using this is only displaying the year th
    record was published, hence why the 'year_published' field is being
    generated.

    ---
    responses:
      200:
        description: A list of dictionaries, each one corresponding to one fact sheet in the
    """

    q = db.select(
        FactSheets.internal_id, FactSheets.fact_sheet_name, FactSheets.analyte, FactSheets.document_type,
        FactSheets.functional_classes,
        RecordInfo.source, RecordInfo.link, func.count(Contents.dtxsid)
    ).join_from(
        FactSheets, RecordInfo, FactSheets.internal_id == RecordInfo.internal_id
    ).join_from(
        RecordInfo, Contents, RecordInfo.internal_id == Contents.internal_id, isouter=True
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

    return jsonify({"results": results})


@app.get("/api/amos/method_list")
def method_list():
    """
    Endpoint for retrieving a list of all the methods present in the database.

    ---
    responses:
      200:
        description: A list of dictionaries, each one corresponding to one method in the database.
    """

    q = db.select(
        Methods.internal_id, Methods.method_name, Methods.method_number, Methods.date_published, Methods.matrix,
        Methods.analyte,
        Methods.functional_classes, Methods.pdf_metadata, RecordInfo.source, RecordInfo.methodologies,
        RecordInfo.description,
        RecordInfo.link, Methods.document_type, Methods.publisher, func.count(Contents.dtxsid)
    ).join_from(
        Methods, RecordInfo, Methods.internal_id == RecordInfo.internal_id
    ).join_from(
        RecordInfo, Contents, RecordInfo.internal_id == Contents.internal_id, isouter=True
    ).group_by(
        Methods.internal_id, RecordInfo.internal_id
    )

    results = [r._asdict() for r in db.session.execute(q).all()]
    results = [{**r, "year_published": util.clean_year(r["date_published"])} for r in results]
    for r in results:
        if pm := r.get("pdf_metadata"):
            r["author"] = pm.get("Author", None)
            r["limitation"] = pm.get("Limitation", None)
            r["limit_of_detection"] = pm.get("Limit of Detection", None)
            r["limit_of_quantitation"] = pm.get("Limit of Quantitation", None)
            del r["pdf_metadata"]
        else:
            r["author"] = None

    return {"results": results}


@app.get("/api/amos/get_pdf/<record_type>/<internal_id>")
def get_pdf(record_type, internal_id):
    """
    Retrieve a PDF from the database by the internal ID and type of record.

    ---
    parameters:
      - in: path
        name: record_type
        type: string
        description: A string indicating which kind of record is being retrieved.  Valid values are 'fact sheet', 'method', and 'spectrum pdf'.
      - in: path
        name: internal_id
        type: integer
        description: ID of the document in the database.
    responses:
      200:
        description: The PDF being searched, in the form of an <iframe>-compatible element.
    """

    pdf_content = cq.pdf_by_id(internal_id, record_type.lower())

    if pdf_content:
        response = make_response(pdf_content)
        response.headers['Content-Type'] = "application/pdf"
        response.headers['Content-Disposition'] = f"inline; filename=\"{internal_id}.pdf\""
        return response
    else:
        return f"Error: no PDF found for internal ID '{internal_id}'."


@app.get("/api/amos/get_pdf_metadata/<record_type>/<internal_id>")
def get_pdf_metadata(record_type, internal_id):
    """
    Retrieves metadata associated with a PDF.

    Both fact sheets and methods have
    associated metadata, so this uses the record_type argument to differentiate
    between them.

    ---
    parameters:
      - in: path
        name: record_type
        type: string
        description: A string indicating which kind of record is being retrieved. Valid values are 'fact sheet' and 'method'.
      - in: path
        name: internal_id
        type: integer
        description: ID of the document in the database.
    responses:
      200:
        description: A JSON structure containing the metadata, the name, and whether the method has associated spectra.
    """

    metadata = cq.pdf_metadata(internal_id, record_type.lower())
    if metadata is not None:
        return jsonify(metadata)
    else:
        return f"Error: no PDF found for internal ID '{internal_id}'."


@app.get("/api/amos/find_dtxsids/<internal_id>")
def find_dtxsids(internal_id):
    """
    Returns a list of DTXSIDs associated with the specified internal ID
    Along with additional substance information. This is mostly used for pulling back
    information on the substances listed in a method or fact sheet.

    ---
    parameters:
      - in: path
        name: internal_id
        type: integer
        description: ID of the document in the database.
    responses:
      200:
        description: A JSON structure containing a list of substance information.  This will be empty if no records were found.
    """

    substance_list = cq.substances_for_ids(internal_id)
    if len(substance_list) == 0:
        print(f"Warning -- no DTXSIDs found for internal ID {internal_id}")
    return jsonify({"substance_list": substance_list})


@app.get("/api/amos/substance_similarity_search/<dtxsid>")
def find_similar_substances(dtxsid, similarity_threshold=0.8):
    """
    Makes a call to an EPA-built API for substance similarity
     And returns the list of DTXSIDs of substances with a similarity measure at or above the
    `similarity_threshold` parameter.

    ---
    parameters:
      - in: path
        name: dtxsid
        type: string
        description: The DTXSID to search on.
      - in: path
        name: similarity_threshold
        type: float
        description: A value from 0 to 1, sent to an EPA API as a threshold for how similar the substances you're searching for should be.  Higher values will return only highly similar substances.
    responses:
      200:
        description: A list of similar substances, or None if none were found.
    """

    BASE_URL = f"{ccte_api_server}/similar-compound/by-dtxsid/"

    # workaround for [SSL: UNSAFE_LEGACY_RENEGOTIATION_DISABLED]
    # https://stackoverflow.com/questions/71603314/ssl-error-unsafe-legacy-renegotiation-disabled
    url = f"{BASE_URL}{dtxsid}/{similarity_threshold}"
    logging.info(f"Calling {url}")
    response = get_legacy_session().get(url)

    if response.status_code == 200:
        return {"similar_substance_info": response.json()}
    else:
        print("Error: ", response.status_code)
        return {"similar_substance_info": None}


@app.get("/api/amos/get_similar_structures/<dtxsid>")
def get_similar_structures(dtxsid):
    """
    Searches the database for all methods which contain at least one substance of sufficient similarity to the searched substance.
    The searched similarity level is hardcoded here, and I currently have no plans to make it adjustable by the app.

    ---
    parameters:
      - in: path
        name: dtxsid
        type: string
        description: The DTXSID to search on.
    responses:
      200:
        description: A JSON structure containing information on the related methods.
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

    methods_query = db.select(
        Contents.internal_id, Contents.dtxsid, RecordInfo.source, RecordInfo.methodologies,
        Methods.method_name, Methods.date_published
    ).filter(
        Contents.dtxsid.in_(similar_dtxsids)
    ).join_from(
        Contents, RecordInfo, Contents.internal_id == RecordInfo.internal_id
    ).join_from(
        Contents, Methods, Contents.internal_id == Methods.internal_id
    )
    method_results = [c._asdict() for c in db.session.execute(methods_query).all()]

    fact_sheet_query = db.select(
        Contents.internal_id, Contents.dtxsid, RecordInfo.source, FactSheets.fact_sheet_name
    ).filter(
        Contents.dtxsid.in_(similar_dtxsids)
    ).join_from(
        Contents, RecordInfo, Contents.internal_id == RecordInfo.internal_id
    ).join_from(
        Contents, FactSheets, Contents.internal_id == FactSheets.internal_id
    )
    fact_sheet_results = [c._asdict() for c in db.session.execute(fact_sheet_query).all()]

    methods_with_searched_substance = [r["internal_id"] for r in method_results if r["dtxsid"] == dtxsid]
    fact_sheets_with_searched_substance = [r["internal_id"] for r in fact_sheet_results if r["dtxsid"] == dtxsid]
    dtxsid_names = cq.names_for_dtxsids([r["dtxsid"] for r in method_results + fact_sheet_results])

    # merge info, supply a boolean for whether the searched substance is in the
    # method, and parse the publication year
    method_results = [{
        **r, "similarity": similarity_dict[r["dtxsid"]], "substance_name": dtxsid_names.get(r["dtxsid"]),
        "has_searched_substance": r["internal_id"] in methods_with_searched_substance,
        "year_published": util.clean_year(r["date_published"]),
        "methodology": ", ".join(r["methodologies"]) if r["methodologies"] is not None else None
    } for r in method_results]
    ids_to_method_names = {r["internal_id"]: r["method_name"] for r in method_results}

    fact_sheet_results = [{
        **r, "similarity": similarity_dict[r["dtxsid"]], "substance_name": dtxsid_names.get(r["dtxsid"]),
        "has_searched_substance": r["internal_id"] in fact_sheets_with_searched_substance
    } for r in fact_sheet_results]
    ids_to_fact_sheet_names = {r["internal_id"]: r["fact_sheet_name"] for r in fact_sheet_results}

    method_dtxsid_counts = Counter([r["dtxsid"] for r in method_results])
    fact_sheet_dtxsid_counts = Counter([r["dtxsid"] for r in fact_sheet_results])
    dtxsid_counts = [{"dtxsid": k, "num_methods": method_dtxsid_counts.get(k, 0),
                      "num_fact_sheets": fact_sheet_dtxsid_counts.get(k, 0), "preferred_name": v,
                      "similarity": similarity_dict[k]} for k, v in dtxsid_names.items()]

    return jsonify({
        "method_results": method_results, "fact_sheet_results": fact_sheet_results,
        "ids_to_method_names": ids_to_method_names, "ids_to_fact_sheet_names": ids_to_fact_sheet_names,
        "dtxsid_counts": dtxsid_counts
    })


@app.post("/api/amos/batch_search")
def batch_search():
    """
    Receives a list of DTXSIDs and returns information on all records in the
    database that contain those DTXSIDs.  If a record contains more than one of
    the searched DTXSIDs, then that record will appear once for each searched
    substance it contains.
    ---
    parameters:
      - in: body
        name: body
        schema:
            id: BatchSearchRequest
            properties:
              base_url:
                type: string
              dtxsids:
                type: array
                example: [DTXSID123]
                description: List of DTXSIDs to search for.
                items:
                  type: string
              include_classyfire:
                type: boolean
              include_external_links:
                type: boolean
              methodologies:
                type: array
                items:
                  type: string
              record_types:
                type: array
                items:
                  type: string
              additional_record_info:
                type: boolean
              include_source_counts:
                type: boolean
              include_functional_uses:
                type: boolean
              always_download_file:
                type: boolean
    responses:
      200:
        description: OK
    """
    parameters = request.get_json()
    base_url = parameters["base_url"]
    dtxsid_list = parameters["dtxsids"]
    include_classyfire = parameters["include_classyfire"]
    include_external_links = parameters["include_external_links"]
    methodologies = parameters["methodologies"]
    record_types = parameters["record_types"]
    additional_record_info = parameters["additional_record_info"]
    include_source_counts = parameters["include_source_counts"]
    include_functional_uses = parameters["include_functional_uses"]
    always_download_file = parameters["always_download_file"]

    #### PART 1: Fire off the initial queries to the database for record counts. ####

    substance_query = db.select(Substances.dtxsid, Substances.casrn, Substances.preferred_name).filter(
        Substances.dtxsid.in_(dtxsid_list))
    substance_df = pd.DataFrame([c._asdict() for c in db.session.execute(substance_query).all()])

    record_query = db.select(
        Contents.internal_id, Contents.dtxsid, RecordInfo.methodologies, RecordInfo.source, RecordInfo.link,
        RecordInfo.record_type, RecordInfo.description, RecordInfo.data_type
    ).join_from(
        Contents, RecordInfo, Contents.internal_id == RecordInfo.internal_id
    ).filter(Contents.dtxsid.in_(dtxsid_list))

    if not methodologies["all"]:
        accepted_methodologies = [k for k, v in methodologies.items() if (k != "all") and v]
        record_query = record_query.filter(
            or_(*[RecordInfo.methodologies.contains([am]) for am in accepted_methodologies]))

    accepted_record_types = [k for k, v in record_types.items() if (k != "all") and v]
    record_query = record_query.filter(RecordInfo.record_type.in_(accepted_record_types))
    records = [c._asdict() for c in db.session.execute(record_query).all()]

    if not include_external_links:
        # don't add this as a filter to the query; it'll miss records without sources if it's added there
        records = [r for r in records if r["data_type"] is not None]
    for i, r in enumerate(records):
        if href := util.construct_internal_href(r['internal_id'], r['record_type'], r['data_type']):
            records[i]["AMOS Link"] = base_url + href

    #### PART 2: Construct the dataframe for the record info, if there are records to get info for. ####

    if len(records) == 0:
        if always_download_file:
            record_df = pd.DataFrame([], columns=[
                "dtxsid", "casrn", "preferred_name", "internal_id", "methodologies", "source",
                "record_type", "AMOS Link", "link", "count", "description"
            ])
            result_df = pd.DataFrame([], columns=[
                "DTXSID", "CASRN", "Substance Name", "AMOS Record ID", "Methodologies", "Source",
                "Record Type", "AMOS Link", "Source Link", "# Substances in Record", "Description"
            ])
        else:
            return Response(status=204)
    else:
        record_df = pd.DataFrame(records)
        record_df.drop("data_type", axis=1, inplace=True)

        # add counts of substances per record
        found_record_ids = set(record_df["internal_id"])
        substances_per_record = cq.substance_counts_by_record(found_record_ids)
        substances_per_record_df = pd.DataFrame(substances_per_record)
        record_df = record_df.merge(substances_per_record_df, how="left", on="internal_id")

        # render methodologies as a delimited string rather than printing the list object
        has_methodology = ~record_df["methodologies"].isna()
        record_df.loc[has_methodology, "methodologies"] = record_df.loc[has_methodology, "methodologies"].apply(
            lambda x: "; ".join(x))

        result_df = substance_df.merge(record_df, how="right", on="dtxsid")
        result_df = result_df[[
            "dtxsid", "casrn", "preferred_name", "internal_id", "methodologies", "source", "record_type",
            "AMOS Link", "link", "count", "description"
        ]]

        # add additional mass spectrum info, if requested
        ms_info_flags = additional_record_info["ms"]
        if any([v for _, v in ms_info_flags.items()]):
            ms_info_query = db.select(
                MassSpectra.internal_id, MassSpectra.spectral_entropy, MassSpectra.normalized_entropy,
                MassSpectra.spectrum_metadata,
                func.array_length(MassSpectra.spectrum, 1).label("num_peaks")
            ).filter(MassSpectra.internal_id.in_(found_record_ids))
            ms_info = pd.DataFrame([c._asdict() for c in db.session.execute(ms_info_query).all()])
            ms_info["rating"] = ms_info.apply(
                lambda x: spectrum.spectrum_rating(x.spectral_entropy, x.normalized_entropy), axis=1)
            ms_info["ionization_mode"] = ms_info["spectrum_metadata"].apply(
                lambda x: x["Spectrometry"].get("Ion Mode") if x.get("Spectrometry") else None)

            if ms_info_flags["all"]:
                ms_info = ms_info[["internal_id", "ionization_mode", "rating", "spectral_entropy", "num_peaks"]]
            else:
                ms_info = ms_info[["internal_id"] + [k for k, v in ms_info_flags.items() if v]]
            ms_info.rename({"ionization_mode": "Ionization Mode", "rating": "Spectrum Rating",
                            "spectral_entropy": "Spectral Entropy", "num_peaks": "# Peaks"}, axis=1, inplace=True)
            result_df = result_df.merge(ms_info, how="left", on="internal_id")

        result_df.rename({
            "dtxsid": "DTXSID", "casrn": "CASRN", "preferred_name": "Substance Name", "internal_id": "AMOS Record ID",
            "source": "Source",
            "record_type": "Record Type", "description": "Description", "link": "Source Link",
            "methodologies": "Methodologies",
            "count": "# Substances in Record"
        }, axis=1, inplace=True)

    result_counts = record_df.groupby(["dtxsid"]).size().reset_index()
    result_counts.columns = ["dtxsid", "num_records"]
    result_counts = pd.DataFrame({"dtxsid": dtxsid_list}).merge(substance_df, how="left", on="dtxsid").merge(
        result_counts, how="left", on="dtxsid")
    result_counts["num_records"] = result_counts["num_records"].fillna(0)

    # add more substance info, if appropriate
    if include_classyfire:
        classyfire_query = db.select(
            ClassyFire.dtxsid, ClassyFire.kingdom, ClassyFire.superklass, ClassyFire.klass, ClassyFire.subklass
        ).filter(ClassyFire.dtxsid.in_(dtxsid_list))
        classyfire_results = [c._asdict() for c in db.session.execute(classyfire_query).all()]
        classyfire_df = pd.DataFrame(classyfire_results)
        result_counts = result_counts.merge(classyfire_df, how="left", on="dtxsid")

    if include_source_counts:
        source_counts = cq.additional_source_counts(dtxsid_list)
        source_count_df = pd.DataFrame(source_counts)
        source_count_df.rename({
            "literature_count": "Articles", "patent_count": "Patents", "source_count": "Sources",
            "pubmed_count": "PubMed Record Count"
        }, axis=1, inplace=True)
        result_counts = result_counts.merge(source_count_df, how="left", on="dtxsid")

    if include_functional_uses:
        functional_use_classes = cq.functional_uses_for_dtxsids(dtxsid_list)
        functional_use_df = pd.DataFrame([(k, "; ".join(v) if v else None) for k, v in functional_use_classes.items()],
                                         columns=["dtxsid", "Functional Use Classes"])
        result_counts = result_counts.merge(functional_use_df, how="left", on="dtxsid")

    result_counts.rename({
        "dtxsid": "DTXSID", "casrn": "CASRN", "preferred_name": "Substance Name", "num_records": "# of Records",
        "kingdom": "Kingdom", "superklass": "Superclass", "klass": "Class", "subklass": "Subclass"
    }, axis=1, inplace=True)

    excel_file = util.make_excel_file({"Substances": result_counts, "Records": result_df})
    headers = {"Content-Disposition": "attachment; filename=batch_search.xlsx",
               "Content-type": "application/vnd.ms-excel"}
    return Response(excel_file, mimetype="application/vnd.ms-excel", headers=headers)


@app.post("/api/amos/analytical_qc_batch_search")
def analytical_qc_batch_search():
    """
    Receives a list of DTXSIDs
    And returns information on all Analytical QC records that contain those DTXSIDs.
    ---
    parameters:
      - in: body
        name: body
        schema:
            id: analytical_qc_batch_search_request
            properties:
                base_url:
                  type: string
                dtxsids:
                  type: array
                  items:
                    type: string
                include_classyfire:
                    type: boolean
                include_source_counts:
                    type: boolean
                methodologies:
                  type: array
                  items:
                    type: string
                include_source_counts:
                    type: boolean
                include_functional_uses:
                    type: boolean
    responses:
      200:
        description: OK
    """
    parameters = request.get_json()
    dtxsid_list = parameters["dtxsids"]
    include_classyfire = parameters["include_classyfire"]
    methodologies = parameters["methodologies"]
    base_url = parameters["base_url"]
    include_source_counts = parameters["include_source_counts"]
    include_functional_uses = parameters["include_functional_uses"]

    substance_query = db.select(Substances.dtxsid, Substances.casrn, Substances.preferred_name).filter(
        Substances.dtxsid.in_(dtxsid_list))
    substances = [c._asdict() for c in db.session.execute(substance_query).all()]
    substance_df = pd.DataFrame(substances)

    record_query = db.select(
        Contents.internal_id, Contents.dtxsid, RecordInfo.methodologies, RecordInfo.link, RecordInfo.description
    ).join_from(
        Contents, RecordInfo, Contents.internal_id == RecordInfo.internal_id
    ).filter(Contents.dtxsid.in_(dtxsid_list) & (RecordInfo.source == "Analytical QC"))

    if not methodologies["all"]:
        accepted_methodologies = [k for k, v in methodologies.items() if (k != "all") and v]
        record_query = record_query.filter(
            or_(*[RecordInfo.methodologies.contains([am]) for am in accepted_methodologies]))

    records = [c._asdict() for c in db.session.execute(record_query).all()]
    if len(records) == 0:
        return Response(status=204)

    record_df = pd.DataFrame(records)
    record_df["methodologies"] = record_df["methodologies"].apply(lambda x: x[0])
    record_df["AMOS Link"] = record_df["internal_id"].apply(lambda x: f"{base_url}/view_spectrum_pdf/{x}")

    result_df = substance_df.merge(record_df, how="right", on="dtxsid")

    result_counts = record_df.groupby(["dtxsid"]).size().reset_index()
    result_counts.columns = ["dtxsid", "num_records"]
    result_counts = pd.DataFrame({"dtxsid": dtxsid_list}).merge(substance_df, how="left", on="dtxsid").merge(
        result_counts, how="left", on="dtxsid")
    result_counts["num_records"] = result_counts["num_records"].fillna(0)

    # add more substance info, if appropriate
    if include_classyfire:
        classyfire_query = db.select(
            ClassyFire.dtxsid, ClassyFire.kingdom, ClassyFire.superklass, ClassyFire.klass, ClassyFire.subklass
        ).filter(ClassyFire.dtxsid.in_(dtxsid_list))
        classyfire_results = [c._asdict() for c in db.session.execute(classyfire_query).all()]
        classyfire_df = pd.DataFrame(classyfire_results)
        result_counts = result_counts.merge(classyfire_df, how="left", on="dtxsid")

    if include_source_counts:
        source_counts = cq.additional_source_counts(dtxsid_list)
        source_count_df = pd.DataFrame(source_counts)
        source_count_df.rename({
            "literature_count": "Articles", "patent_count": "Patents", "source_count": "Sources",
            "pubmed_count": "PubMed Record Count"
        }, axis=1, inplace=True)
        result_counts = result_counts.merge(source_count_df, how="left", on="dtxsid")

    if include_functional_uses:
        functional_use_classes = cq.functional_uses_for_dtxsids(dtxsid_list)
        functional_use_df = pd.DataFrame([(k, "; ".join(v) if v else None) for k, v in functional_use_classes.items()],
                                         columns=["dtxsid", "Functional Use Classes"])
        result_counts = result_counts.merge(functional_use_df, how="left", on="dtxsid")

    analytical_qc_query = db.select(
        AnalyticalQC.internal_id, AnalyticalQC.first_timepoint, AnalyticalQC.last_timepoint,
        AnalyticalQC.stability_call, AnalyticalQC.timepoint
    ).join_from(AnalyticalQC, Contents, AnalyticalQC.internal_id == Contents.internal_id).filter(
        Contents.dtxsid.in_(dtxsid_list))
    analytical_qc_results = [c._asdict() for c in db.session.execute(analytical_qc_query).all()]
    analytical_qc_df = pd.DataFrame(analytical_qc_results)
    result_df = result_df.merge(analytical_qc_df, how="left", on="internal_id")

    result_df = result_df[[
        "dtxsid", "casrn", "preferred_name", "internal_id", "methodologies", "AMOS Link", "link", "description",
        "first_timepoint",
        "last_timepoint", "stability_call", "timepoint"
    ]]
    result_df.rename({
        "dtxsid": "DTXSID", "casrn": "CASRN", "preferred_name": "Substance Name", "internal_id": "AMOS Record ID",
        "description": "Description", "link": "Source Link", "methodologies": "Methodologies",
        "first_timepoint": "First Timepoint",
        "last_timepoint": "Last Timepoint", "stability_call": "Stability Call", "timepoint": "Measurement Timepoint"
    }, axis=1, inplace=True)
    result_counts.rename({
        "dtxsid": "DTXSID", "casrn": "CASRN", "preferred_name": "Substance Name", "num_records": "# of Records",
        "kingdom": "Kingdom", "superklass": "Superclass", "klass": "Class", "subklass": "Subclass"
    }, axis=1, inplace=True)

    excel_file = util.make_excel_file({"Substances": result_counts, "Records": result_df})
    headers = {"Content-Disposition": "attachment; filename=batch_search.xlsx",
               "Content-type": "application/vnd.ms-excel"}
    return Response(excel_file, mimetype="application/vnd.ms-excel", headers=headers)


@app.get("/api/amos/method_with_spectra/<search_type>/<internal_id>")
def method_with_spectra_search(search_type, internal_id):
    """
    Attempts to return information about a method with linked spectra.
    Searching is done using the internal ID of either the method or one of its spectra.

    ---
    parameters:
      - in: path
        name: search_type
        type: string
        description: Search type
      - in: path
        name: internal_id
        type: integer
        description: The unique internal identifier for the spectrum that's being looked for.
    responses:
      200:
        description: A JSON structure containing the information about the spectrum.
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
        Contents, Substances, Contents.dtxsid == Substances.dtxsid
    )
    info_entries = [c._asdict() for c in db.session.execute(info_q).all()]

    return jsonify({"method_id": method_id, "spectrum_ids": spectrum_list, "info": info_entries})


@app.post("/api/amos/spectrum_count_for_methodology/")
def get_spectrum_count_for_methodology():
    """
    Counts the number spectra that have the specified methodology as one of its methodologies.

    Spectra from a variety of methodologies are present in the database; however, all but a few edge cases will be one of GC/MS, LC/MS, NMR, or IR.  The returned counts will also include spectra stored as PDFs, not just those stored directly in the database.

    This endpoint is currently handled by a POST rather than a GET operation due to the fact that a lot of methodologies have forward slashes in them (e.g., 'LC/MS'), which disrupts routing.

    Currently intended for use with applications outside the Vue app.
    ---
    parameters:
        - in: body
          name: body
          schema:
              id: spectrum_count_for_methodology_request
              properties:
                  dtxsid:
                    type: string
                    description: DTXSID for the substance of interest.
                  spectrum_type:
                    type: string
                    description: Analytical methodology to search for.
                    example: GC/MS
    responses:
      200:
        description: OK
    """

    dtxsid = request.get_json()["dtxsid"]
    spectrum_type = request.get_json()["spectrum_type"]

    q = db.select(Contents.internal_id).filter(
        RecordInfo.methodologies.contains([spectrum_type]) & (RecordInfo.record_type == "Spectrum") & (
                Contents.dtxsid == dtxsid)
    ).join_from(Contents, RecordInfo, Contents.internal_id == RecordInfo.internal_id)
    return jsonify({"count": len(db.session.execute(q).all())})


@app.post("/api/amos/substances_for_ids/")
def get_substances_for_ids():
    """
    Accepts a list of internal_ids (via POST) and returns a deduplicated list substances that appear in those records.
    ---
    parameters:
      - in: body
        name: body
        schema:
            id: substances_for_ids_request
            properties:
                internal_id_list:
                    type: array
                    items:
                        type: string
    responses:
      200:
        description: OK
    """

    internal_id_list = request.get_json()["internal_id_list"]

    substances = cq.substances_for_ids(internal_id_list, [Substances.jchem_inchikey])
    substance_df = pd.DataFrame(substances)

    excel_file = util.make_excel_file({"Substances": substance_df})
    headers = {"Content-Disposition": "attachment; filename=Substances.xlsx",
               "Content-type": "application/vnd.ms-excel"}
    return Response(excel_file, mimetype="application/vnd.ms-excel", headers=headers)


@app.post("/api/amos/count_substances_in_ids/")
def count_substances_in_ids():
    """
    Counts the number of unique substances seen in a given set of internal IDs.
    ---
    parameters:
      - in: body
        name: body
        schema:
            id: count_substances_in_ids_request
            properties:
                internal_id_list:
                    type: array
                    items:
                        type: string
    responses:
      200:
        description: OK
    """
    internal_id_list = request.get_json()["internal_id_list"]
    q = db.select(func.count(Contents.dtxsid.distinct())).filter(Contents.internal_id.in_(internal_id_list))
    dtxsid_count = db.session.execute(q).first()._asdict()
    return jsonify(dtxsid_count)


@app.post("/api/amos/mass_spectrum_similarity_search/")
def mass_spectrum_similarity_search():
    """
    Takes a mass range, methodology, and mass spectrum, and returns all spectra that match the mass and methodology, with entropy similarities between the database spectra and the user-supplied one.
    ---
    parameters:
      - in: body
        name: body
        schema:
            id: mass_spectrum_similarity_search_request
            properties:
                lower_mass_limit:
                    type: number
                upper_mass_limit:
                    type: number
                methodology:
                    type: string
                spectrum:
                    type: object
    responses:
      200:
        description: OK
    """
    request_json = request.get_json()
    lower_mass_limit = request_json["lower_mass_limit"]
    upper_mass_limit = request_json["upper_mass_limit"]
    methodology = request.json["methodology"]
    user_spectrum = request.json["spectrum"]

    results = cq.mass_spectrum_search(lower_mass_limit, upper_mass_limit, methodology)

    substance_mapping = {}
    for r in results:
        if request_json["type"].lower() == "da":
            r["similarity"] = spectrum.calculate_entropy_similarity(r["spectrum"], user_spectrum,
                                                                    da_error=request_json["window"])
        else:
            r["similarity"] = spectrum.calculate_entropy_similarity(r["spectrum"], user_spectrum,
                                                                    ppm_error=request_json["window"])
        if r["similarity"] >= 0.1:
            substance_mapping[r["dtxsid"]] = r["preferred_name"]
        del r["preferred_name"]
    results = [r for r in results if
               r["similarity"] >= 0.1]  # since the frontend will only ever show stuff with a similarity of at least 0.1
    return jsonify({"result_length": len(results), "unique_substances": len(substance_mapping), "results": results,
                    "substance_mapping": substance_mapping})


@app.post("/api/amos/spectral_entropy/")
def spectral_entropy():
    """
    Calculates the spectral entropy for a single spectrum.
    ---
    parameters:
      - in: body
        name: body
        schema:
            id: spectral_entropy_request
            properties:
                spectrum:
                    type: array
                    description: Array of m/z intensity pairs.  Should be formatted as an array of two-element arrays, each of which has the m/z value and the intensity value (in that order).
                    example: [[10.5, 20], [20, 100], [50, 1]]

    responses:
      200:
        description: OK
    """
    entropy = spectrum.calculate_spectral_entropy(request.get_json()["spectrum"])
    return jsonify({"entropy": entropy})


@app.post("/api/amos/entropy_similarity/")
def entropy_similarity():
    """
    Calculates the entropy similarity for two spectra.
    ---
    parameters:
      - in: body
        name: body
        schema:
            id: entropy_similarity_request
            properties:
                spectrum1:
                    type: array
                    description: Array of m/z intensity pairs.  Should be formatted as an array of two-element arrays, each of which has the m/z value and the intensity value (in that order).
                    example: [[10.5, 20], [20, 100], [50, 1]]
                spectrum2:
                    type: array
                    description: Array of m/z intensity pairs.  Should be formatted as an array of two-element arrays, each of which has the m/z value and the intensity value (in that order).
                    example: [[10.5, 20], [20, 100], [50, 1]]
                type:
                    type: string
                    description: Type of mass window to use.  Should be either "da" or "ppm".
                window:
                    type: number
                    description: Size of the mass window to use.

    responses:
      200:
        description: OK
    """
    post_data = request.get_json()
    print(post_data.get("type"))
    if post_data.get("type") is None:
        similarity = spectrum.calculate_entropy_similarity(post_data["spectrum_1"], post_data["spectrum_2"])
    elif post_data["type"].lower() == "da":
        print(post_data["window"])
        similarity = spectrum.calculate_entropy_similarity(post_data["spectrum_1"], post_data["spectrum_2"],
                                                           da_error=post_data["window"])
    else:
        similarity = spectrum.calculate_entropy_similarity(post_data["spectrum_1"], post_data["spectrum_2"],
                                                           ppm_error=post_data["window"])
    return jsonify({"similarity": similarity})


@app.post("/api/amos/record_counts_by_dtxsid/")
def get_record_counts_by_dtxsid():
    """
    Takes a list of DTXSIDs, and for each DTXSID, it returns a dictionary containing the counts of record types that are present in the database.
    ---
    parameters:
      - in: body
        name: body
        schema:
            id: record_counts_by_dtxsid_request
            properties:
            dtxsids:
                type: array
                items:
                    type: string
    responses:
      200:
        description: OK
    """
    dtxsid_list = request.get_json()["dtxsids"]
    record_count_dict = cq.record_counts_by_dtxsid(dtxsid_list)
    return jsonify(record_count_dict)


@app.post("/api/amos/max_similarity_by_dtxsid/")
def max_similarity_by_dtxsid():
    """
    This endpoint allows a user to submit a list of DTXSIDs and a mass spectrum.
    In response, the user will get back the DTXSIDs mapped to similarity scores.
    The scores will be the highest similarity score computed on the user-supplied spectrum and all spectra in this database for that DTXSID.
    If no spectra were found, the DTXSID will map to None.

    This access point is intended to be used by CFMID.
    ---
    parameters:
      - in: body
        name: body
        schema:
            id: max_similarity_by_dtxsid_request
            properties:
                dtxsids:
                    type: array
                    items:
                        type: string
    responses:
      200:
        description: OK
    """
    request_json = request.get_json()
    dtxsids = request_json["dtxsids"]
    if type(dtxsids) == str:
        dtxsids = [dtxsids]
    user_spectra = request_json["spectra"]
    for i, us in enumerate(user_spectra):
        try:
            spectrum.validate_spectrum(us)
        except ValueError as ve:
            return jsonify({"error": f"User-supplied spectrum number {i + 1} is invalid: {ve}"})

    da = request_json.get("da_window")
    ppm = request_json.get("ppm_window")
    ms_level = request_json.get("ms_level")
    if type(ms_level) != int:
        ms_level = None

    # get the list of spectra in the database for the given substances
    results = cq.mass_spectra_for_substances(dtxsids, ms_level=ms_level)

    substance_dict = {d: [None] * len(user_spectra) for d in dtxsids}
    for i, us in enumerate(user_spectra):
        for r in results:
            similarity = spectrum.calculate_entropy_similarity(us, r["spectrum"], da_error=da, ppm_error=ppm)
            if substance_dict[r["dtxsid"]][i] is None or substance_dict[r["dtxsid"]][i] < similarity:
                substance_dict[r["dtxsid"]][i] = similarity

    return jsonify({"results": substance_dict})


@app.post("/api/amos/all_similarities_by_dtxsid/")
def all_similarities_by_dtxsid():
    request_json = request.get_json()
    dtxsids = request_json["dtxsids"]
    if type(dtxsids) == str:
        dtxsids = [dtxsids]
    user_spectra = request_json["spectra"]
    for i, us in enumerate(user_spectra):
        try:
            spectrum.validate_spectrum(us)
        except ValueError as ve:
            return jsonify({"error": f"User-supplied spectrum number {i + 1} is invalid: {ve}"})

    da = request_json.get("da_window")
    ppm = request_json.get("ppm_window")
    min_intensity = request_json.get("min_intensity", 0)
    ms_level = request_json.get("ms_level")
    if type(ms_level) != int:
        ms_level = None

    results = cq.mass_spectra_for_substances(dtxsids, ms_level=ms_level,
                                             additional_fields=[MassSpectra.spectrum_metadata])

    # mass query
    q = db.select(Substances.dtxsid, Substances.monoisotopic_mass).filter(Substances.dtxsid.in_(dtxsids))
    mass_results = [c._asdict() for c in db.session.execute(q).all()]
    mass_dict = {mr["dtxsid"]: mr["monoisotopic_mass"] for mr in mass_results}

    similarity_list = []
    for us in user_spectra:
        us = [[mz, i] for mz, i in us if i > min_intensity]
        substance_dict = {d: [] for d in dtxsids}
        for r in results:
            # filter out peaks above the monoisotopic mass (minus a proton or so) and peaks below a certain intensity
            result_spectrum = [[mz, i] for mz, i in r["spectrum"] if
                               (mz < (mass_dict[r["dtxsid"]] - 1.5)) and (i > min_intensity)]
            if len(result_spectrum) == 0:
                continue
            if r["description"].startswith("#"):
                description = None
            else:
                description = ";".join(r["description"].split(";")[:-1])
            combined_spectrum = spectrum.combine_peaks(result_spectrum)
            spectral_entropy = spectrum.calculate_spectral_entropy(combined_spectrum)
            normalized_entropy = spectral_entropy / len(combined_spectrum)
            information = {"Points": len(result_spectrum), "Spectral Entropy": spectral_entropy,
                           "Normalized Entropy": normalized_entropy,
                           "Rating": spectrum.spectrum_rating(spectral_entropy, normalized_entropy)}
            entropy_similarity = spectrum.calculate_entropy_similarity(us, combined_spectrum, da_error=da,
                                                                       ppm_error=ppm)
            cosine_similarity = spectrum.cosine_similarity(us, combined_spectrum)
            substance_dict[r["dtxsid"]].append(
                {"entropy_similarity": entropy_similarity, "cosine_similarity": cosine_similarity,
                 "description": description, "metadata": r["spectrum_metadata"], "information": information})
        similarity_list.append(substance_dict)

    return jsonify({"results": similarity_list})


@app.get("/api/amos/get_info_by_id/<internal_id>")
def get_info_by_id(internal_id):
    """
    Return information by internal record id
    ---
    parameters:
      - in: path
        name: internal_id
        type: string
        description: ID of the document in the database.
    responses:
      200:
        description: Record information.
    """
    q = db.select(RecordInfo).filter(RecordInfo.internal_id == internal_id)
    result = db.session.execute(q).first()
    if result:
        return jsonify({"result": result[0].get_row_contents()})
    else:
        return jsonify({"result": None})


@app.get("/api/amos/database_summary/")
def database_summary():
    """
    Return database summary information.
    ---
    responses:
      200:
        description: Database summary information.
    """
    summary_info = cq.database_summary()
    return jsonify(summary_info)


@app.post("/api/amos/mass_spectra_for_substances/")
def mass_spectra_for_substances():
    """
    Given a list of DTXSIDs, return all spectra for those substances.
    ---
    parameters:
      - in: body
        name: dtxsids
        required: true
        schema:
          type: array
          items:
            type: string
    responses:
      200:
        description: OK
    """
    dtxsids = request.get_json()["dtxsids"]
    spectrum_results = cq.mass_spectra_for_substances(dtxsids)
    names_for_dtxsids = cq.names_for_dtxsids(dtxsids)
    return jsonify({"spectra": spectrum_results, "substance_mapping": names_for_dtxsids})


@app.get("/api/amos/get_image_for_dtxsid/<dtxsid>")
def get_image_for_dtxsid(dtxsid):
    """
    Retrieves a substance's image from the database.
    ---
    parameters:
      - in: path
        name: dtxsid
        type: string
        description: DTXSID of the substance.
    responses:
      200:
        description: PNG image of the substance
    """
    q = db.select(SubstanceImages.png_image).filter(SubstanceImages.dtxsid == dtxsid)
    result = db.session.execute(q).first()
    if result is not None:
        image = result.png_image
        response = make_response(image)
        response.headers['Content-Type'] = "image/png"
        response.headers['Content-Disposition'] = f"inline; filename=\"{dtxsid}\".png"
        return response
    else:
        return Response(status=204)


@app.get("/api/amos/substring_search/<substring>")
def substring_search(substring):
    """
    Searches the database for substances by substring.
    Both the preferred name and the synonyms are searched. This returns a list
    of substances, synonyms that matched the search (if any), and the
    record counts for each substance.
    ---
    parameters:
      - in: path
        name: substring
        type: string
        description: A string to search by
    responses:
      200:
        description: List of substances, synonyms that matched the search (if any), and the record counts for each substance
    """

    preferred_names, synonyms = cq.substring_search(substring)

    info_dict = {}
    for pn in preferred_names:
        info_dict[pn["dtxsid"]] = {"synonyms": [], **pn}
    for s in synonyms:
        if s["dtxsid"] in info_dict:
            info_dict[s["dtxsid"]]["synonyms"].append(s["synonym"])
        else:
            info_dict[s["dtxsid"]] = {**s, "synonyms": [s["synonym"]]}
            del info_dict[s["dtxsid"]]["synonym"]
    info_list = [v for _, v in info_dict.items()]

    dtxsids = [il["dtxsid"] for il in info_list]
    record_counts = cq.record_counts_by_dtxsid(dtxsids)
    full_info = util.merge_substance_info_and_counts(info_list, record_counts)

    return jsonify({"substances": full_info})


@app.get("/api/amos/get_ms_ready_methods/<inchikey>")
def get_ms_ready_methods(inchikey):
    """
    Retrieves a list of methods that contain the MS-Ready forms of a given substance but not the substance itself.
    These methods are found by looking for substances which match the first block of the given InChIKey.
    ---
    parameters:
      - in: path
        name: inchikey
        type: string
        description: InChIKey to search by
    responses:
      200:
        description: List of MS-Ready methods.
    """
    first_block = inchikey.split("-")[0]
    q = db.select(
        RecordInfo.source, RecordInfo.internal_id, RecordInfo.link, RecordInfo.record_type, RecordInfo.methodologies,
        RecordInfo.data_type, RecordInfo.description, func.count(Contents.dtxsid)
    ).filter(
        Substances.jchem_inchikey.like(first_block + "%") & (Substances.jchem_inchikey != inchikey)
    ).join_from(
        Contents, Substances, Contents.dtxsid == Substances.dtxsid
    ).join_from(
        Contents, RecordInfo, Contents.internal_id == RecordInfo.internal_id
    ).group_by(
        RecordInfo.internal_id
    )
    results = [c._asdict() for c in db.session.execute(q).all()]

    internal_ids = [c["internal_id"] for c in results]
    method_number_query = db.select(Methods.internal_id, Methods.method_number).filter(
        Methods.internal_id.in_(internal_ids))
    method_numbers = [r._asdict() for r in db.session.execute(method_number_query)]
    method_numbers = {mn["internal_id"]: mn["method_number"] for mn in method_numbers}

    for r in results:
        r["ms_ready"] = True  # flag for Ag Grid
        if r["internal_id"] in method_numbers:
            r["method_number"] = method_numbers[r["internal_id"]]

    return jsonify({"length": len(results), "results": results})


@app.get("/api/amos/get_substance_file_for_record/<internal_id>")
def get_substance_file_for_record(internal_id):
    """
    Creates an Excel workbook listing the substances in the specified record.
    ---
    parameters:
      - in: path
        name: internal_id
        type: integer
        description: Internal database ID of the record.
    responses:
      200:
        description: Excel workbook listing the substances in the specified record.
    """
    substance_list = find_dtxsids(internal_id).json["substance_list"]
    substance_list = [(sl["dtxsid"], sl["casrn"], sl["preferred_name"]) for sl in substance_list]
    substance_df = pd.DataFrame(substance_list, columns=["DTXSID", "CASRN", "Preferred Name"])

    excel_file = util.make_excel_file({"Substances": substance_df})
    headers = {"Content-Disposition": "attachment; filename=substances.xlsx",
               "Content-type": "application/vnd.ms-excel"}
    return Response(excel_file, mimetype="application/vnd.ms-excel", headers=headers)


@app.get("/api/amos/analytical_qc_list/")
def analytical_qc_list():
    """
    Retrieves information on all the AnalyticalQC PDFs in the database.
    ---
    responses:
      200:
        description: AnalyticalQC PDFs in the database.
    """
    q = db.select(
        Contents.internal_id, Contents.dtxsid, Substances.preferred_name, Substances.casrn,
        Substances.molecular_formula,
        AnalyticalQC.experiment_date, AnalyticalQC.timepoint, AnalyticalQC.first_timepoint, AnalyticalQC.last_timepoint,
        AnalyticalQC.stability_call, AnalyticalQC.annotation, AnalyticalQC.study, AnalyticalQC.sample_id,
        AnalyticalQC.lcms_amen_pos_true, AnalyticalQC.lcms_amen_neg_true, AnalyticalQC.flags
    ).join_from(
        AnalyticalQC, Contents, AnalyticalQC.internal_id == Contents.internal_id
    ).join_from(
        Contents, Substances, Contents.dtxsid == Substances.dtxsid
    )
    results = [c._asdict() for c in db.session.execute(q).all()]
    return jsonify({"results": results})


@app.get("/api/amos/additional_sources_for_substance/<dtxsid>")
def additional_sources_for_substance(dtxsid):
    """
    Retrieves links for supplemental sources (e.g., Wikipedia, ChemExpo) for a given DTXSID.
    ---
    parameters:
      - in: path
        name: dtxsid
        type: string
        description: DTXSID of the substance.
    responses:
      200:
        description: Links for supplemental sources (e.g., Wikipedia, ChemExpo)
    """
    sources = cq.additional_sources_by_substance(dtxsid)
    return jsonify(sources)


@app.route("/api/amos/get_nmr_spectrum/<internal_id>")
def retrieve_nmr_spectrum(internal_id):
    """
    Endpoint for retrieving a specified NMR spectrum from the database.
    ---
    parameters:
      - in: path
        name: internal_id
        type: integer
        description: The unique internal identifier for the spectrum that's being looked for.
    responses:
      200:
        description: A JSON structure containing the information about the spectrum.
    """
    q = db.select(
        NMRSpectra.intensities, NMRSpectra.first_x, NMRSpectra.last_x, NMRSpectra.x_units,
        NMRSpectra.frequency, NMRSpectra.nucleus, NMRSpectra.temperature, NMRSpectra.solvent,
        NMRSpectra.spectrum_metadata
    ).filter(NMRSpectra.internal_id == internal_id)
    data_row = db.session.execute(q).first()
    if data_row is not None:
        data_dict = data_row._asdict()
        return jsonify(data_dict)

    else:
        return "Error: invalid internal id."


@app.get("/api/amos/get_classification_for_dtxsid/<dtxsid>")
def get_classification_for_dtxsid(dtxsid):
    """
    Returns the classification of a given substance.
    ---
    parameters:
      - in: path
        name: dtxsid
        type: string
        description: DTXSID of the substance.
    responses:
      200:
        description: JSON with classification information.
    """
    classification_info = cq.classyfire_for_dtxsid(dtxsid)
    if classification_info is not None:
        return jsonify(classification_info)
    else:
        return Response(status=204)


@app.post("/api/amos/substances_for_classification/")
def substances_for_classification():
    request_json = request.get_json()
    kingdom, superklass, klass, subklass = request_json.get("kingdom"), request_json.get(
        "superklass"), request_json.get("klass"), request_json.get("subklass")
    query = db.select(
        ClassyFire.dtxsid, Substances.casrn, Substances.preferred_name, Substances.monoisotopic_mass,
        Substances.molecular_formula,
        Substances.image_in_comptox
    ).join_from(ClassyFire, Substances, ClassyFire.dtxsid == Substances.dtxsid).filter(
        (ClassyFire.kingdom == kingdom) & (ClassyFire.superklass == superklass) & (ClassyFire.klass == klass) & (
                ClassyFire.subklass == subklass)
    )
    substances = [c._asdict() for c in db.session.execute(query).all()]
    dtxsids = [s["dtxsid"] for s in substances]

    record_counts = cq.record_counts_by_dtxsid(dtxsids)
    for s in substances:
        records = record_counts[s["dtxsid"]]
        s["methods"] = records.get("Method", 0)
        s["fact_sheets"] = records.get("Fact Sheet", 0)
        s["spectra"] = records.get("Spectrum", 0)

    return jsonify({"substances": substances})


@app.post("/api/amos/next_level_classification/")
def next_level_classification():
    request_json = request.get_json()
    kingdom, superklass, klass = request_json.get("kingdom"), request_json.get("superklass"), request_json.get("klass")

    if kingdom is not None:
        if superklass is not None:
            if klass is not None:
                query = db.select(ClassyFire.subklass).filter(
                    (ClassyFire.kingdom == kingdom) & (ClassyFire.superklass == superklass) & (
                            ClassyFire.klass == klass)
                ).distinct().order_by(ClassyFire.subklass)
            else:
                query = db.select(ClassyFire.klass).filter(
                    (ClassyFire.kingdom == kingdom) & (ClassyFire.superklass == superklass)
                ).distinct(ClassyFire.klass)
        else:
            query = db.select(ClassyFire.superklass).filter(ClassyFire.kingdom == kingdom).distinct().order_by(
                ClassyFire.superklass)
    else:
        return jsonify({"error": "No kingdom was passed."})

    possible_values = [r[0] for r in db.session.execute(query)]
    return jsonify({"values": possible_values})


@app.get("/api/amos/fact_sheets_for_substance/<dtxsid>")
def fact_sheets_for_substance(dtxsid):
    """
    Returns a list of fact sheets that are associated with the given DTXSID.
    ---
    parameters:
      - in: path
        name: dtxsid
        type: string
        description: DTXSID of the substance.
    responses:
      200:
        description: List of fact sheets.
    """
    info_list = cq.ids_for_substances([dtxsid], record_type="Fact Sheet")
    fact_sheet_ids = [r["internal_id"] for r in info_list]
    return jsonify({"internal_ids": fact_sheet_ids})


@app.get("/api/amos/get_data_source_info/")
def data_source_info():
    """
    Returns a list of major data sources in AMOS with some supplemental information.
    ---
    responses:
      200:
        description: JSON with the list of major data sources
    """
    query = db.select(DataSourceInfo)
    return [c[0].get_row_contents() for c in db.session.execute(query).all()]


@app.get("/api/amos/record_id_search/<internal_id>")
def record_id_search(internal_id):
    """
    Record information by ID
    ---
    parameters:
      - in: path
        name: internal_id
        type: integer
        description: The unique internal identifier for the spectrum that's being looked for.
    responses:
      200:
        description: A JSON structure containing the information about the record.
    """
    id_query = db.select(RecordInfo.record_type, RecordInfo.data_type, RecordInfo.link).filter(
        RecordInfo.internal_id == internal_id)
    result = db.session.execute(id_query).first()
    if result:
        return jsonify({"record_type": result.record_type, "data_type": result.data_type, "link": result.link})
    else:
        return jsonify({"record_type": None, "data_type": None, "link": None})


@app.get("/api/amos/functional_uses_for_dtxsid/<dtxsid>")
def functional_uses_for_dtxsid(dtxsid):
    """
    Returns a list of functional uses for a substance
    ---
    parameters:
      - in: path
        name: dtxsid
        type: string
        description: DTXSID of the substance.
    responses:
      200:
        description: List of functional uses.
    """

    """query = db.select(FunctionalUseClasses.functional_classes).filter(FunctionalUseClasses.dtxsid==dtxsid)
    result = db.session.execute(query).first()
    if result:
        return jsonify(result._asdict())
    else:
        return jsonify({"functional_classes": None})"""
    functional_use_dict = cq.functional_uses_for_dtxsids([dtxsid])
    return jsonify({"functional_classes": functional_use_dict.get(dtxsid, None)})


@app.get("/api/amos/dtxsids_for_functional_use/<functional_use>")
def dtxsids_for_functional_use(functional_use):
    """
    Returns a list of DTXSIDs for the given functional use.
    ---
    parameters:
      - in: path
        name: functional_use
        type: string
        description: Functional use to search by
    responses:
      200:
        description: List of DTXSIDs for the given functional use.
    """
    query = db.select(FunctionalUseClasses.dtxsid).filter(FunctionalUseClasses.functional_classes.any(functional_use))
    dtxsid_list = [c.dtxsid for c in db.session.execute(query).all()]
    return jsonify({"dtxsids": dtxsid_list})


@app.get("/api/amos/formula_search/<formula>")
def formula_search(formula):
    """
    Returns a list of substances found by MF
    ---
    parameters:
      - in: path
        name: formula
        type: string
        description: Molecular furmula to search by.
    responses:
      200:
        description: List of DTXSIDs for the given functional use.
    """
    substances = cq.formula_search(formula)
    dtxsids = [s["dtxsid"] for s in substances]
    record_counts = cq.record_counts_by_dtxsid(dtxsids)
    full_info = util.merge_substance_info_and_counts(substances, record_counts)
    return jsonify({"substances": full_info})


@app.get("/api/amos/inchikey_first_block_search/<first_block>")
def inchikey_first_block_search(first_block):
    """
    Returns a list of substances found by InChI key.
    ---
    parameters:
      - in: path
        name: first_block
        type: string
        description: First block of InChI key to search by.
    responses:
      200:
        description: List of substances found by InChI key.
    """
    substances = cq.inchikey_first_block_search(first_block)
    dtxsids = [s["dtxsid"] for s in substances]
    record_counts = cq.record_counts_by_dtxsid(dtxsids)
    full_info = util.merge_substance_info_and_counts(substances, record_counts)
    return jsonify({"substances": full_info})


@app.get("/api/amos/get_ir_spectrum/<internal_id>")
def get_ir_spectrum(internal_id):
    """
    Returns a list of IR spectra by ID.
    ---
    parameters:
      - in: path
        name: internal_id
        type: integer
        description: The unique internal identifier for the spectrum that's being looked for.
    responses:
      200:
        description: A JSON structure containing the information about the IR spectrum.
    """
    q = db.select(
        InfraredSpectra.first_x, InfraredSpectra.intensities, InfraredSpectra.ir_type,
        InfraredSpectra.laser_frequency, InfraredSpectra.last_x, InfraredSpectra.spectrum_metadata
    ).filter(InfraredSpectra.internal_id == internal_id)
    data_row = db.session.execute(q).first()
    if data_row is not None:
        data_dict = data_row._asdict()
        return jsonify(data_dict)
    else:
        return "Error: invalid internal id."


@app.post("/api/amos/mass_range_search/")
def mass_range_search():
    request_json = request.get_json()
    lower_mass_limit = request_json["lower_mass_limit"]
    upper_mass_limit = request_json["upper_mass_limit"]
    substances = cq.mass_range_search(lower_mass_limit, upper_mass_limit)
    dtxsids = [s["dtxsid"] for s in substances]
    record_counts = cq.record_counts_by_dtxsid(dtxsids)
    full_info = util.merge_substance_info_and_counts(substances, record_counts)
    return jsonify({"substances": full_info})


@app.get("/api/amos/record_type_count/<record_type>")
def record_type_count(record_type):
    """
    Returns the number of records of the given type.
    ---
    parameters:
      - in: path
        name: record_type
        type: string
        description: Record type to search by
    responses:
      200:
        description: Count of record types.
    """
    possible_record_types = {"analytical_qc", "fact_sheets", "methods"}
    if record_type in possible_record_types:
        if record_type == "methods":
            query = db.select(func.count(Methods.internal_id))
        elif record_type == "analytical_qc":
            query = db.select(func.count(AnalyticalQC.internal_id))
        else:
            query = db.select(func.count(FactSheets.internal_id))
        record_count = db.session.execute(query).first()[0]
        return jsonify({"record_count": record_count})
    else:
        return Response(status=204)


@app.get("/api/amos/method_pagination/<limit>/<offset>")
def method_pagination(limit, offset):
    """
    Returns a paginated list of methods.
    ---
    parameters:
      - in: path
        name: limit
        type: integer
        description: Limit of records to return.
      - in: path
        name: offset
        type: integer
        description: Offset of method records to return.
    responses:
      200:
        description: Methods information
    """
    q = db.select(
        Methods.internal_id, Methods.method_name, Methods.method_number, Methods.date_published, Methods.matrix,
        Methods.analyte,
        Methods.functional_classes, Methods.pdf_metadata, RecordInfo.source, RecordInfo.methodologies,
        RecordInfo.description,
        RecordInfo.link, Methods.document_type, Methods.publisher, func.count(Contents.dtxsid)
    ).join_from(
        Methods, RecordInfo, Methods.internal_id == RecordInfo.internal_id
    ).join_from(
        RecordInfo, Contents, RecordInfo.internal_id == Contents.internal_id, isouter=True
    ).group_by(
        Methods.internal_id, RecordInfo.internal_id
    ).order_by(Methods.internal_id).limit(limit).offset(offset)

    results = [r._asdict() for r in db.session.execute(q).all()]
    results = [{**r, "year_published": util.clean_year(r["date_published"])} for r in results]
    for r in results:
        if pm := r.get("pdf_metadata"):
            r["author"] = pm.get("Author", None)
            r["limitation"] = pm.get("Limitation", None)
            r["limit_of_detection"] = pm.get("Limit of Detection", None)
            r["limit_of_quantitation"] = pm.get("Limit of Quantitation", None)
            del r["pdf_metadata"]
        else:
            r["author"] = None

    return {"results": results}


@app.get("/api/amos/fact_sheet_pagination/<limit>/<offset>")
def fact_sheet_pagination(limit, offset):
    """
    Returns a paginated list of fact sheets.
    ---
    parameters:
      - in: path
        name: limit
        type: integer
        description: Limit of records to return.
      - in: path
        name: offset
        type: integer
        description: Offset of fact sheets to return.
    responses:
      200:
        description: Fact sheets information
    """
    q = db.select(
        FactSheets.internal_id, FactSheets.fact_sheet_name, FactSheets.analyte, FactSheets.document_type,
        FactSheets.functional_classes,
        RecordInfo.source, RecordInfo.link, func.count(Contents.dtxsid)
    ).join_from(
        FactSheets, RecordInfo, FactSheets.internal_id == RecordInfo.internal_id
    ).join_from(
        RecordInfo, Contents, RecordInfo.internal_id == Contents.internal_id, isouter=True
    ).group_by(
        FactSheets.internal_id, RecordInfo.internal_id
    ).order_by(FactSheets.internal_id).limit(limit).offset(offset)
    results = [r._asdict() for r in db.session.execute(q).all()]

    single_dtxsid_ids = [r["internal_id"] for r in results if r["count"] == 1]
    q2 = db.select(Contents.internal_id, Contents.dtxsid).filter(Contents.internal_id.in_(single_dtxsid_ids))
    single_dtxsid_results = {r.internal_id: r.dtxsid for r in db.session.execute(q2).all()}

    for i in range(len(results)):
        if results[i]["internal_id"] in single_dtxsid_results:
            results[i]["dtxsid"] = single_dtxsid_results[results[i]["internal_id"]]

    return jsonify({"results": results})


@app.get("/api/amos/analytical_qc_pagination/<limit>/<offset>")
def analytical_qc_pagination(limit, offset):
    """
        Returns a paginated list of Analytical QC.
        ---
        parameters:
          - in: path
            name: limit
            type: integer
            description: Limit of records to return.
          - in: path
            name: offset
            type: integer
            description: Offset of the records to return.
        responses:
          200:
            description: List of Analytical QC.
        """
    q = db.select(
        Contents.internal_id, Contents.dtxsid, Substances.preferred_name, Substances.casrn,
        Substances.molecular_formula,
        AnalyticalQC.experiment_date, AnalyticalQC.timepoint, AnalyticalQC.first_timepoint, AnalyticalQC.last_timepoint,
        AnalyticalQC.stability_call, AnalyticalQC.annotation, AnalyticalQC.study, AnalyticalQC.sample_id,
        AnalyticalQC.lcms_amen_pos_true, AnalyticalQC.lcms_amen_neg_true, AnalyticalQC.flags
    ).join_from(
        AnalyticalQC, Contents, AnalyticalQC.internal_id == Contents.internal_id
    ).join_from(
        Contents, Substances, Contents.dtxsid == Substances.dtxsid
    ).order_by(AnalyticalQC.internal_id).limit(limit).offset(offset)
    results = [c._asdict() for c in db.session.execute(q).all()]
    return jsonify({"results": results})


db.init_app(app)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
