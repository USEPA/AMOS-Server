from collections import Counter
from enum import Enum
import io
import re
from time import time

from flask import Flask, jsonify, request, send_file, make_response
from flask_cors import CORS

from table_definitions import db, MonaMain, MonaAdditionalInfo, MonaSpectra, \
    CFSREMain, CFSREAdditionalInfo, CFSREMonograph, \
    SpectrabaseMain, SpectrabaseAdditionalInfo, \
    MassbankMain, MassbankAdditionalInfo, MassbankSpectra, \
    SWGMain, SWGAdditionalInfo, SWGMonograph, \
    SWGMSMain, SWGMSAdditionalInfo, SWGMSSpectra, \
    ECMMain, ECMAdditionalInfo, ECMMethods, \
    AgilentMain, AgilentAdditionalInfo, AgilentMethods, \
    IDTable

DB_DIRECTORY = "../db/"
MONA_DB = DB_DIRECTORY + "mona.db"
SPECTRABASE_DB = DB_DIRECTORY + "spectrabase.db"
CFSRE_DB = DB_DIRECTORY + "cfsre.db"
ECM_DB = DB_DIRECTORY + "ecm.db"
MASSBANK_DB = DB_DIRECTORY + "massbank_eu.db"
SWG_MONOGRAPH_DB = DB_DIRECTORY + "swg.db"
SWG_SPECTRA_DB = DB_DIRECTORY + "swg_ms.db"
AGILENT_DB = DB_DIRECTORY + "agilent.db"
ID_DB = DB_DIRECTORY + "id.db"

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{ID_DB}"
app.config["SQLALCHEMY_BINDS"] = {
    'mona': f"sqlite:///{MONA_DB}",
    'spectrabase': f"sqlite:///{SPECTRABASE_DB}",
    'cfsre': f"sqlite:///{CFSRE_DB}",
    'ecm': f"sqlite:///{ECM_DB}",
    'massbank': f"sqlite:///{MASSBANK_DB}",
    'swg_mono': f"sqlite:///{SWG_MONOGRAPH_DB}",
    'swg_ms': f"sqlite:///{SWG_SPECTRA_DB}",
    'agilent': f"sqlite:///{AGILENT_DB}"
}

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = "secretkey"

CORS(app, resources={r'/*': {'origins': '*'}})

db.init_app(app)

class SearchType(Enum):
    InChIKey = 1
    CASRN = 2
    CompoundName = 3
    DTXSID = 4


@app.route("/")
def top_page():
    return "<p>Hello, World!</p>"


@app.route("/search/<search_term>")
def search_results(search_term):
    # currently ignoring the search type argument from the URL, as selecting the
    # search type currently hasn't been implemented
    search_type = determine_search_type(search_term)
    
    t1 = time()
    mona_results = mona_search(search_type, search_term)
    print("Got MoNA")
    t1_sb = time()
    spectrabase_results = spectrabase_search(search_type, search_term)
    t2_sb = time()
    print("Got Spectrabase")
    print("Spectrabase time: ", t2_sb - t1_sb)
    cfsre_results = cfsre_search(search_type, search_term)
    print("Got CFSRE")
    massbank_results = massbank_search(search_type, search_term)
    print("Got Massbank")
    swg_mono_results = swg_monograph_search(search_type, search_term)
    print("Got SWG monographs")
    swg_ms_results = swg_ms_search(search_type, search_term)
    print("Got SWG spectra")
    ecm_results = ecm_search(search_type, search_term)
    print("Got ECM")
    agilent_results = agilent_search(search_type, search_term)
    print("Got Agilent")
    t2 = time()
    print("Elapsed time: ", t2-t1)
    

    results = []
    for r in [mona_results, spectrabase_results, cfsre_results, massbank_results, swg_mono_results, swg_ms_results, ecm_results, agilent_results]:
        results.extend(r)

    record_type = request.args.get("record_type")

    dtxsids = [r["dtxsid"] for r in results if r["dtxsid"] is not None]
    if dtxsids:
        most_common_dtxsid = Counter(dtxsids).most_common(1)[0][0]
        id_query = db.select(IDTable).filter(IDTable.dtxsid==most_common_dtxsid)
        id_results = db.session.execute(id_query).all()
        if len(id_results) > 0:
            id_row = id_results[0][0]
            id_info = {"dtxsid": id_row.dtxsid, "casrn": id_row.casrn,
                       "inchikey": id_row.inchikey,
                       "preferred_name": id_row.preferred_name,
                       "molecular_formula":id_row.molecular_formula,
                       "molecular_weight":id_row.molecular_weight}
        else:
            id_info = {"dtxsid": None, "casrn": None, "inchikey": None,
                       "preferred_name": None, "molecular_formula": None,
                       "molecular_weight": None}
    else:
        id_info = {"dtxsid": None, "casrn": None, "inchikey": None,
                   "preferred_name": None, "molecular_formula": None,
                   "molecular_weight": None}

    return jsonify({"search_term": search_term,
                    "search_type": search_type.name,
                    "results": results,
                    "id_info":id_info})


def determine_search_type(search_term):
    """
    Determine whether the search term in question is an InChIKey, CAS
    number, or a name.  Expecting this to be imprecise at best,
    especially early on.

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


def mona_search(search_type, search_value):
    q = db.select(MonaMain.dtxsid,MonaMain.name, MonaMain.cas_number, MonaMain.inchikey,
                  MonaAdditionalInfo.spectrum_type, MonaAdditionalInfo.source, 
                  MonaAdditionalInfo.internal_id, MonaAdditionalInfo.link, MonaMain.record_type,
                  MonaAdditionalInfo.data_type)
    
    if search_type == SearchType.InChIKey:
        inchikey_first_block = search_value[:14]
        q = q.filter(MonaMain.inchikey.like(inchikey_first_block+"%"))
    elif search_type == SearchType.CASRN:
        q = q.filter(MonaMain.cas_number==search_value)
    elif search_type == SearchType.CompoundName:
        q = q.filter(MonaMain.name.ilike(search_value))
    elif search_type == SearchType.DTXSID:
        q = q.filter(MonaMain.dtxsid==search_value)
    
    q = q.join_from(MonaMain, MonaAdditionalInfo,
                    MonaMain.internal_id==MonaAdditionalInfo.internal_id)
    
    results = db.session.execute(q).all()
    
    return [r._asdict() for r in results]


def spectrabase_search(search_type, search_value):
    q = db.select(SpectrabaseMain.dtxsid, SpectrabaseMain.name, SpectrabaseMain.cas_number, SpectrabaseMain.inchikey,
                  SpectrabaseAdditionalInfo.spectrum_type, SpectrabaseAdditionalInfo.source, 
                  SpectrabaseAdditionalInfo.internal_id, SpectrabaseAdditionalInfo.link, SpectrabaseMain.record_type,
                  SpectrabaseAdditionalInfo.data_type)
    
    q = q.filter(SpectrabaseMain.dtxsid != None)
    
    if search_type == SearchType.InChIKey:
        inchikey_first_block = search_value[:14]
        q = q.filter(SpectrabaseMain.inchikey.like(inchikey_first_block+"%"))
    elif search_type == SearchType.CASRN:
        q = q.filter(SpectrabaseMain.cas_number==search_value)
    elif search_type == SearchType.CompoundName:
        q = q.filter(SpectrabaseMain.name.ilike(search_value))
    elif search_type == SearchType.DTXSID:
        q = q.filter(SpectrabaseMain.dtxsid==search_value)
    
    q = q.join_from(SpectrabaseMain, SpectrabaseAdditionalInfo,
                    SpectrabaseMain.internal_id==SpectrabaseAdditionalInfo.internal_id)
    
    results = db.session.execute(q).all()
    
    return [r._asdict() for r in results]


def cfsre_search(search_type, search_value):
    q = db.select(CFSREMain.dtxsid, CFSREMain.name, CFSREMain.cas_number, CFSREMain.inchikey,
                  CFSREAdditionalInfo.spectrum_type, CFSREAdditionalInfo.source, 
                  CFSREAdditionalInfo.internal_id, CFSREAdditionalInfo.link, CFSREMain.record_type,
                  CFSREAdditionalInfo.data_type)
    
    if search_type == SearchType.InChIKey:
        inchikey_first_block = search_value[:14]
        q = q.filter(CFSREMain.inchikey.like(inchikey_first_block+"%"))
    elif search_type == SearchType.CASRN:
        q = q.filter(CFSREMain.cas_number==search_value)
    elif search_type == SearchType.CompoundName:
        q = q.filter(CFSREMain.name.ilike(search_value))
    elif search_type == SearchType.DTXSID:
        q = q.filter(CFSREMain.dtxsid==search_value)
    
    q = q.join_from(CFSREMain, CFSREAdditionalInfo,
                    CFSREMain.internal_id==CFSREAdditionalInfo.internal_id)
    
    results = db.session.execute(q).all()
    
    return [r._asdict() for r in results]


def massbank_search(search_type, search_value):
    q = db.select(MassbankMain.dtxsid, MassbankMain.name, MassbankMain.cas_number, MassbankMain.inchikey,
                  MassbankAdditionalInfo.spectrum_type, MassbankAdditionalInfo.source, 
                  MassbankAdditionalInfo.internal_id, MassbankAdditionalInfo.link, MassbankMain.record_type,
                  MassbankAdditionalInfo.data_type)
    
    if search_type == SearchType.InChIKey:
        inchikey_first_block = search_value[:14]
        q = q.filter(MassbankMain.inchikey.like(inchikey_first_block+"%"))
    elif search_type == SearchType.CASRN:
        q = q.filter(MassbankMain.cas_number==search_value)
    elif search_type == SearchType.CompoundName:
        q = q.filter(MassbankMain.name.ilike(search_value))
    elif search_type == SearchType.DTXSID:
        q = q.filter(MassbankMain.dtxsid==search_value)
    
    q = q.join_from(MassbankMain, MassbankAdditionalInfo,
                    MassbankMain.internal_id==MassbankAdditionalInfo.internal_id)
    
    results = db.session.execute(q).all()
    
    return [r._asdict() for r in results]


def swg_ms_search(search_type, search_value):
    q = db.select(SWGMSMain.dtxsid, SWGMSMain.name, SWGMSMain.cas_number, SWGMSMain.inchikey,
                  SWGMSAdditionalInfo.spectrum_type, SWGMSAdditionalInfo.source, 
                  SWGMSAdditionalInfo.internal_id, SWGMSAdditionalInfo.link, SWGMSMain.record_type,
                  SWGMSAdditionalInfo.data_type)
    
    if search_type == SearchType.InChIKey:
        inchikey_first_block = search_value[:14]
        q = q.filter(SWGMSMain.inchikey.like(inchikey_first_block+"%"))
    elif search_type == SearchType.CASRN:
        q = q.filter(SWGMSMain.cas_number==search_value)
    elif search_type == SearchType.CompoundName:
        q = q.filter(SWGMSMain.name.ilike(search_value))
    elif search_type == SearchType.DTXSID:
        q = q.filter(SWGMSMain.dtxsid==search_value)
    
    q = q.join_from(SWGMSMain, SWGMSAdditionalInfo,
                    SWGMSMain.internal_id==SWGMSAdditionalInfo.internal_id)
    
    results = db.session.execute(q).all()
    
    return [r._asdict() for r in results]


def swg_monograph_search(search_type, search_value):
    q = db.select(SWGMain.dtxsid, SWGMain.name, SWGMain.cas_number, SWGMain.inchikey,
                  SWGAdditionalInfo.spectrum_type, SWGAdditionalInfo.source, 
                  SWGAdditionalInfo.internal_id, SWGAdditionalInfo.link, SWGMain.record_type,
                  SWGAdditionalInfo.data_type)
    
    if search_type == SearchType.InChIKey:
        inchikey_first_block = search_value[:14]
        q = q.filter(SWGMain.inchikey.like(inchikey_first_block+"%"))
    elif search_type == SearchType.CASRN:
        q = q.filter(SWGMain.cas_number==search_value)
    elif search_type == SearchType.CompoundName:
        q = q.filter(SWGMain.name.ilike(search_value))
    elif search_type == SearchType.DTXSID:
        q = q.filter(SWGMain.dtxsid==search_value)
    
    q = q.join_from(SWGMain, SWGAdditionalInfo,
                    SWGMain.internal_id==SWGAdditionalInfo.internal_id)
    
    results = db.session.execute(q).all()
    
    return [r._asdict() for r in results]


def ecm_search(search_type, search_value):
    q = db.select(ECMMain.dtxsid, ECMMain.name, ECMMain.cas_number, ECMMain.inchikey,
                  ECMAdditionalInfo.spectrum_type, ECMAdditionalInfo.source, 
                  ECMAdditionalInfo.internal_id, ECMAdditionalInfo.link, ECMMain.record_type,
                  ECMAdditionalInfo.data_type)
    
    if search_type == SearchType.InChIKey:
        inchikey_first_block = search_value[:14]
        q = q.filter(ECMMain.inchikey.like(inchikey_first_block+"%"))
    elif search_type == SearchType.CASRN:
        q = q.filter(ECMMain.cas_number==search_value)
    elif search_type == SearchType.CompoundName:
        q = q.filter(ECMMain.name.ilike(search_value))
    elif search_type == SearchType.DTXSID:
        q = q.filter(ECMMain.dtxsid==search_value)
    
    q = q.join_from(ECMMain, ECMAdditionalInfo,
                    ECMMain.internal_id==ECMAdditionalInfo.internal_id)
    results = db.session.execute(q).all()
    
    return [r._asdict() for r in results]


def agilent_search(search_type, search_value):
    q = db.select(AgilentMain.dtxsid, AgilentMain.name, AgilentMain.cas_number, AgilentMain.inchikey,
                  AgilentAdditionalInfo.spectrum_type, AgilentAdditionalInfo.source, 
                  AgilentAdditionalInfo.internal_id, AgilentAdditionalInfo.link, AgilentMain.record_type,
                  AgilentAdditionalInfo.data_type)
    
    if search_type == SearchType.InChIKey:
        inchikey_first_block = search_value[:14]
        q = q.filter(AgilentMain.inchikey.like(inchikey_first_block+"%"))
    elif search_type == SearchType.CASRN:
        q = q.filter(AgilentMain.cas_number==search_value)
    elif search_type == SearchType.CompoundName:
        q = q.filter(AgilentMain.name.ilike(search_value))
    elif search_type == SearchType.DTXSID:
        q = q.filter(AgilentMain.dtxsid==search_value)
    
    q = q.join_from(AgilentMain, AgilentAdditionalInfo,
                    AgilentMain.internal_id==AgilentAdditionalInfo.internal_id)
    results = db.session.execute(q).all()
    
    return [r._asdict() for r in results]


@app.route("/monograph_list")
def monograph_list():
    ## Note: In the returned data, 'info_source' is a sort of sub-source, as both CFSRE and SWG
    ## seem to aggregate monographs from a couple different sources.  The 'record_source' field
    ## is used for internally identifying whether a record is in the CFSRE or SWG database.
    filenames = []
    monograph_info = []

    ## info for CFSRE monographs
    q = db.select(CFSREMonograph.internal_id)
    results = db.session.execute(q).all()
    cfsre_filenames = [p.internal_id[:-4] for p in results]
    cfsre_monograph_info = []
    for fn in cfsre_filenames:
        fn_match = re.match("^(.*)_([0-9]{6})_(.*)$", fn)
        cfsre_monograph_info.append({"name":fn_match.groups()[0], "date":fn_match.groups()[1], "info_source":fn_match.groups()[2], "filename":fn, "record_source":"CFSRE"})
    filenames.extend(cfsre_filenames)
    monograph_info.extend(cfsre_monograph_info)

    ## info for SWG monographs
    q = db.select(SWGMonograph.internal_id)
    results = db.session.execute(q).all()
    swg_filenames = [p.internal_id[:-4] for p in results]
    swg_monograph_info = [{"name":fn, "date":"", "info_source":"Scientific Working Group", "filename":fn, "record_source":"Scientific Working Group"} for fn in swg_filenames]

    filenames.extend(swg_filenames)
    monograph_info.extend(swg_monograph_info)
    
    return jsonify({"names": filenames, "monograph_info": monograph_info})


"""
@app.route("/monograph_list_test")
def monograph_list_test():
    q = db.select(CFSREMonograph.internal_id, CFSREMain.dtxsid).join_from(CFSREMonograph, CFSREMain,
                    CFSREMonograph.internal_id==SpectrabaseAdditionalInfo.internal_id)
    results = db.session.execute(q).all()
"""
    


@app.route("/download/cfsre/<pdf_name>")
def download_cfsre(pdf_name):
    q = db.select(CFSREMonograph.pdf_data).filter(CFSREMonograph.internal_id==pdf_name)
    data_row = db.session.execute(q).first()
    if data_row is not None:
        pdf_content = data_row.pdf_data
        response = make_response(pdf_content)
        response.headers['Content-Type'] = "application/pdf"
        response.headers['Content-Disposition'] = f"inline; filename={pdf_name}"
        return response
    else:
        return "Error: PDF name not found."


@app.route("/download/swg/<pdf_name>")
def download_swg(pdf_name):
    q = db.select(SWGMonograph.pdf_data).filter(SWGMonograph.internal_id==pdf_name)
    data_row = db.session.execute(q).first()
    if data_row is not None:
        pdf_content = io.BytesIO(data_row.pdf_data)
        return send_file(pdf_content,
                         attachment_filename=pdf_name,
                         as_attachment=True)
    else:
        return "Error: PDF name not found."


@app.route("/get_spectrum/<source>/<internal_id>")
def retrieve_spectrum(source, internal_id):
    if source == "MoNA":
        q = db.select(MonaSpectra.spectrum, MonaSpectra.splash, MonaSpectra.normalized_entropy, MonaSpectra.spectral_entropy).filter(MonaSpectra.internal_id==internal_id)
    elif source == "Scientific Working Group":
        q = db.select(SWGMSSpectra.spectrum, SWGMSSpectra.splash, SWGMSSpectra.normalized_entropy, SWGMSSpectra.spectral_entropy).filter(SWGMSSpectra.internal_id==internal_id)
    elif source == "MassBank EU":
        q = db.select(MassbankSpectra.spectrum, MassbankSpectra.splash, MassbankSpectra.normalized_entropy, MassbankSpectra.spectral_entropy).filter(MassbankSpectra.internal_id==internal_id)
    else:
        return "Error: Invalid spectrum source."
    
    data_row = db.session.execute(q).first()
    if data_row is not None:
        spectrum_info = data_row._asdict()
        peaks = spectrum_info["spectrum"].split(" ")
        mz = [float(p.split(":")[0]) for p in peaks]
        intensities = [float(p.split(":")[1]) for p in peaks]
        spectrum = [[m,i] for m, i in zip(mz, intensities)]
        return jsonify({"spectrum": spectrum,
                        "spectral_entropy": spectrum_info["spectral_entropy"],
                        "normalized_entropy": spectrum_info["normalized_entropy"],
                        "splash": spectrum_info["splash"]
                       })
    else:
        return "Error: invalid internal id."


@app.route("/get_pdf/<source>/<internal_id>")
def retrieve_pdf(source, internal_id):
    if source.lower() == "cfsre":
        q = db.select(CFSREMonograph.pdf_data).filter(CFSREMonograph.internal_id==internal_id)
    elif source == "Environmental Chemistry Methods":
        q = db.select(ECMMethods.pdf_data).filter(ECMMethods.internal_id==internal_id)
    elif source == "Scientific Working Group":
        q = db.select(SWGMonograph.pdf_data).filter(SWGMonograph.internal_id==internal_id)
    elif source == "Agilent":
        q = db.select(AgilentMethods.pdf_data).filter(AgilentMethods.internal_id==internal_id)
    else:
        return "Error: Invalid PDF source."
    
    data_row = db.session.execute(q).first()
    if data_row is not None:
        pdf_content = data_row.pdf_data
        response = make_response(pdf_content)
        response.headers['Content-Type'] = "application/pdf"
        response.headers['Content-Disposition'] = f"inline; filename=\"{internal_id}\""
        return response
    else:
        return "Error: PDF name not found."
    

@app.route("/get_pdf_metadata/<source>/<internal_id>")
def retrieve_pdf_metadata(source, internal_id):
    if source == "Environmental Chemistry Methods":
        q = db.select(ECMMethods.method_metadata, ECMMethods.method_name).filter(ECMMethods.internal_id==internal_id)
    elif source == "Agilent":
        q = db.select(AgilentMethods.method_metadata, AgilentMethods.method_name).filter(AgilentMethods.internal_id==internal_id)
    #elif source == "CFSRE":
    #    q = db.select(CFSREMonograph.monograph_metadata).filter(CFSREMonograph.internal_id==internal_id)
    #elif source == "Scientific Working Group":
    #    q = db.select(SWGMonograph.pdf_data).filter(SWGMonograph.internal_id==internal_id)
    else:
        return "Error: Invalid method source."
    
    data_row = db.session.execute(q).first()
    if data_row is not None:
        method_metadata = data_row.method_metadata
        metadata_entries = method_metadata.split(";;")
        metadata_rows = [[x.split("::")[0], x.split("::")[1]] for x in metadata_entries]
        method_name = data_row.method_name
        return jsonify({
            "pdf_metadata": method_metadata,
            "pdf_name": method_name,
            "metadata_rows": metadata_rows
        })
    else:
        return "Error: PDF name not found."
    

@app.route("/find_inchikeys/<inchikey>")
def find_inchikeys(inchikey):
    inchikey_first_block = inchikey[:14]
    all_inchikeys = []
    for x in [MonaMain, CFSREMain, SpectrabaseMain, MassbankMain, SWGMain, SWGMSMain, ECMMain, AgilentMain]:
        q = db.select(x.inchikey).filter(x.inchikey.like(inchikey_first_block+"%"))
        inchikeys = db.session.execute(q).all()
        inchikeys = [i.inchikey for i in inchikeys]
        all_inchikeys.extend(inchikeys)
    unique_inchikeys = set(all_inchikeys)
    print(unique_inchikeys)
    return jsonify({
        "inchikey_present": inchikey in unique_inchikeys,
        "unique_inchikeys": sorted(list(unique_inchikeys))
    })

@app.route("/find_dtxsids/<source>/<internal_id>")
def find_dtxsids(source, internal_id):
    possible_sources = {"scientific working group":SWGMain, "ecm":ECMMain, "cfsre":CFSREMain, "agilent":AgilentMain}
    if source.lower() in possible_sources.keys():
        target_db = possible_sources[source.lower()]
        q = db.select(target_db.dtxsid).filter(target_db.internal_id==internal_id)
        dtxsids = db.session.execute(q).all()
        if len(dtxsids) > 0:
            dtxsids = [d[0] for d in dtxsids]
            q2 = db.select(IDTable.dtxsid, IDTable.preferred_name).filter(IDTable.dtxsid.in_(dtxsids))
            chemical_ids = db.session.execute(q2).all()
            print(chemical_ids)
            return jsonify({"chemical_ids":[c._asdict() for c in chemical_ids]})
        else:
            return f"Unknown error -- no DTXSIDs found for internal ID {internal_id} from source {source}"
    else:
        return f"Unidentified source '{source}'"
