from collections import Counter
from enum import Enum
import io
import re
from time import time

from flask import Flask, jsonify, send_file, make_response
from flask_cors import CORS
import requests

from table_definitions import db, MonaMain, MonaAdditionalInfo, MonaSpectra, \
    CFSREMain, CFSREAdditionalInfo, CFSREMonographs, \
    SpectrabaseMain, SpectrabaseAdditionalInfo, \
    MassbankMain, MassbankAdditionalInfo, MassbankSpectra, \
    SWGMain, SWGAdditionalInfo, SWGMonographs, \
    SWGMSMain, SWGMSAdditionalInfo, SWGMSSpectra, \
    ECMMain, ECMAdditionalInfo, ECMMethods, \
    AgilentMain, AgilentAdditionalInfo, AgilentMethods, \
    OtherMethodsMain, OtherMethodsAdditionalInfo, OtherMethodsMethods, \
    IDTable, Synonyms

DB_DIRECTORY = "./data/db/"
MONA_DB = DB_DIRECTORY + "mona.db"
SPECTRABASE_DB = DB_DIRECTORY + "spectrabase.db"
CFSRE_DB = DB_DIRECTORY + "cfsre.db"
ECM_DB = DB_DIRECTORY + "ecm.db"
MASSBANK_DB = DB_DIRECTORY + "massbank_eu.db"
SWG_MONOGRAPH_DB = DB_DIRECTORY + "swg.db"
SWG_SPECTRA_DB = DB_DIRECTORY + "swg_ms.db"
AGILENT_DB = DB_DIRECTORY + "agilent.db"
OTHER_METHODS_DB = DB_DIRECTORY + "other_methods.db"
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
    'agilent': f"sqlite:///{AGILENT_DB}",
    'other_methods': f"sqlite:///{OTHER_METHODS_DB}"
}

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = "secretkey"

CORS(app, resources={r'/*': {'origins': '*'}})


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
    spectrabase_results = spectrabase_search(search_type, search_term)
    print("Got Spectrabase")
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
    other_methods_results = other_methods_search(search_type, search_term)
    print("Got other methods")
    t2 = time()
    print("Elapsed time: ", t2-t1)
    

    results = []
    for r in [mona_results, spectrabase_results, cfsre_results, massbank_results, swg_mono_results, swg_ms_results, ecm_results, agilent_results, other_methods_results]:
        results.extend(r)
    
    result_record_types = [r["record_type"] for r in results]
    result_record_type_counts = Counter(result_record_types)
    for record_type in ["Method", "Monograph", "Spectrum"]:
        if record_type not in result_record_type_counts:
            result_record_type_counts[record_type] = 0
    result_record_type_counts = {k.lower(): v for k,v in result_record_type_counts.items()}

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
                    "id_info": id_info,
                    "record_type_counts":result_record_type_counts})


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
    base_q = db.select(MonaMain.dtxsid,MonaMain.name, MonaMain.casrn, MonaMain.inchikey,
                       MonaAdditionalInfo.spectrum_type, MonaAdditionalInfo.source, 
                       MonaAdditionalInfo.internal_id, MonaAdditionalInfo.link, MonaMain.record_type,
                       MonaAdditionalInfo.data_type, MonaAdditionalInfo.comment)

    base_q = base_q.filter(MonaMain.dtxsid != None)
    
    if search_type == SearchType.InChIKey:
        q = base_q.filter(MonaMain.inchikey == search_value)
    elif search_type == SearchType.CASRN:
        q = base_q.filter(MonaMain.casrn==search_value)
    elif search_type == SearchType.CompoundName:
        q = base_q.filter(MonaMain.name.ilike(search_value))
    elif search_type == SearchType.DTXSID:
        q = base_q.filter(MonaMain.dtxsid==search_value)
    
    q = q.join_from(MonaMain, MonaAdditionalInfo,
                    MonaMain.internal_id==MonaAdditionalInfo.internal_id)
    
    results = db.session.execute(q).all()

    if (len(results) == 0) and (search_type == SearchType.CompoundName):
        q2 = db.select(Synonyms.dtxsid).filter(Synonyms.synonym.ilike(search_value))
        synonym_results = db.session.execute(q2).all()
        if len(synonym_results) > 0:
            synonym_dtxsid = synonym_results[0].dtxsid
            q_syn = base_q.filter(MonaMain.dtxsid==synonym_dtxsid).join_from(MonaMain, MonaAdditionalInfo,
                    MonaMain.internal_id==MonaAdditionalInfo.internal_id)
            results = db.session.execute(q_syn).all()

    
    return [r._asdict() for r in results]


def spectrabase_search(search_type, search_value):
    base_q = db.select(SpectrabaseMain.dtxsid, SpectrabaseMain.name, SpectrabaseMain.casrn, SpectrabaseMain.inchikey,
                       SpectrabaseAdditionalInfo.spectrum_type, SpectrabaseAdditionalInfo.source, 
                       SpectrabaseAdditionalInfo.internal_id, SpectrabaseAdditionalInfo.link, SpectrabaseMain.record_type,
                       SpectrabaseAdditionalInfo.data_type, SpectrabaseAdditionalInfo.comment)
    
    base_q = base_q.filter(SpectrabaseMain.dtxsid != None)
    
    if search_type == SearchType.InChIKey:
        q = base_q.filter(SpectrabaseMain.inchikey == search_value)
    elif search_type == SearchType.CASRN:
        q = base_q.filter(SpectrabaseMain.casrn==search_value)
    elif search_type == SearchType.CompoundName:
        q = base_q.filter(SpectrabaseMain.name.ilike(search_value))
    elif search_type == SearchType.DTXSID:
        q = base_q.filter(SpectrabaseMain.dtxsid==search_value)
    
    q = q.join_from(SpectrabaseMain, SpectrabaseAdditionalInfo,
                    SpectrabaseMain.internal_id==SpectrabaseAdditionalInfo.internal_id)
    
    results = db.session.execute(q).all()

    if (len(results) == 0) and (search_type == SearchType.CompoundName):
        q2 = db.select(Synonyms.dtxsid).filter(Synonyms.synonym.ilike(search_value))
        synonym_results = db.session.execute(q2).all()
        if len(synonym_results) > 0:
            synonym_dtxsid = synonym_results[0].dtxsid
            q_syn = base_q.filter(SpectrabaseMain.dtxsid==synonym_dtxsid).join_from(SpectrabaseMain, SpectrabaseAdditionalInfo,
                    SpectrabaseMain.internal_id==SpectrabaseAdditionalInfo.internal_id)
            results = db.session.execute(q_syn).all()
    
    return [r._asdict() for r in results]


def cfsre_search(search_type, search_value):
    base_q = db.select(CFSREMain.dtxsid, CFSREMain.name, CFSREMain.casrn, CFSREMain.inchikey,
                       CFSREAdditionalInfo.spectrum_type, CFSREAdditionalInfo.source, 
                       CFSREAdditionalInfo.internal_id, CFSREAdditionalInfo.link, CFSREMain.record_type,
                       CFSREAdditionalInfo.data_type, CFSREAdditionalInfo.comment)
    
    if search_type == SearchType.InChIKey:
        q = base_q.filter(CFSREMain.inchikey == search_value)
    elif search_type == SearchType.CASRN:
        q = base_q.filter(CFSREMain.casrn==search_value)
    elif search_type == SearchType.CompoundName:
        q = base_q.filter(CFSREMain.name.ilike(search_value))
    elif search_type == SearchType.DTXSID:
        q = base_q.filter(CFSREMain.dtxsid==search_value)
    
    q = q.join_from(CFSREMain, CFSREAdditionalInfo,
                    CFSREMain.internal_id==CFSREAdditionalInfo.internal_id)
    
    results = db.session.execute(q).all()
    
    if (len(results) == 0) and (search_type == SearchType.CompoundName):
        q2 = db.select(Synonyms.dtxsid).filter(Synonyms.synonym.ilike(search_value))
        synonym_results = db.session.execute(q2).all()
        if len(synonym_results) > 0:
            synonym_dtxsid = synonym_results[0].dtxsid
            q_syn = base_q.filter(CFSREMain.dtxsid==synonym_dtxsid).join_from(CFSREMain, CFSREAdditionalInfo,
                    CFSREMain.internal_id==CFSREAdditionalInfo.internal_id)
            results = db.session.execute(q_syn).all()

    return [r._asdict() for r in results]


def massbank_search(search_type, search_value):
    base_q = db.select(MassbankMain.dtxsid, MassbankMain.name, MassbankMain.casrn, MassbankMain.inchikey,
                  MassbankAdditionalInfo.spectrum_type, MassbankAdditionalInfo.source, 
                  MassbankAdditionalInfo.internal_id, MassbankAdditionalInfo.link, MassbankMain.record_type,
                  MassbankAdditionalInfo.data_type, MassbankAdditionalInfo.comment)

    base_q = base_q.filter(MassbankMain.dtxsid != None)
    
    if search_type == SearchType.InChIKey:
        q = base_q.filter(MassbankMain.inchikey == search_value)
    elif search_type == SearchType.CASRN:
        q = base_q.filter(MassbankMain.casrn==search_value)
    elif search_type == SearchType.CompoundName:
        q = base_q.filter(MassbankMain.name.ilike(search_value))
    elif search_type == SearchType.DTXSID:
        q = base_q.filter(MassbankMain.dtxsid==search_value)
    
    q = q.join_from(MassbankMain, MassbankAdditionalInfo,
                    MassbankMain.internal_id==MassbankAdditionalInfo.internal_id)
    
    results = db.session.execute(q).all()

    if (len(results) == 0) and (search_type == SearchType.CompoundName):
        q2 = db.select(Synonyms.dtxsid).filter(Synonyms.synonym.ilike(search_value))
        synonym_results = db.session.execute(q2).all()
        if len(synonym_results) > 0:
            synonym_dtxsid = synonym_results[0].dtxsid
            q_syn = base_q.filter(MassbankMain.dtxsid==synonym_dtxsid).join_from(MassbankMain, MassbankAdditionalInfo,
                    MassbankMain.internal_id==MassbankAdditionalInfo.internal_id)
            results = db.session.execute(q_syn).all()
    
    return [r._asdict() for r in results]


def swg_ms_search(search_type, search_value):
    base_q = db.select(SWGMSMain.dtxsid, SWGMSMain.name, SWGMSMain.casrn, SWGMSMain.inchikey,
                       SWGMSAdditionalInfo.spectrum_type, SWGMSAdditionalInfo.source, 
                       SWGMSAdditionalInfo.internal_id, SWGMSAdditionalInfo.link, SWGMSMain.record_type,
                       SWGMSAdditionalInfo.data_type, SWGMSAdditionalInfo.comment)
    
    if search_type == SearchType.InChIKey:
        q = base_q.filter(SWGMSMain.inchikey == search_value)
    elif search_type == SearchType.CASRN:
        q = base_q.filter(SWGMSMain.casrn==search_value)
    elif search_type == SearchType.CompoundName:
        q = base_q.filter(SWGMSMain.name.ilike(search_value))
    elif search_type == SearchType.DTXSID:
        q = base_q.filter(SWGMSMain.dtxsid==search_value)
    
    q = q.join_from(SWGMSMain, SWGMSAdditionalInfo,
                    SWGMSMain.internal_id==SWGMSAdditionalInfo.internal_id)
    
    results = db.session.execute(q).all()

    if (len(results) == 0) and (search_type == SearchType.CompoundName):
        q2 = db.select(Synonyms.dtxsid).filter(Synonyms.synonym.ilike(search_value))
        synonym_results = db.session.execute(q2).all()
        if len(synonym_results) > 0:
            synonym_dtxsid = synonym_results[0].dtxsid
            q_syn = base_q.filter(SWGMSMain.dtxsid==synonym_dtxsid).join_from(SWGMSMain, SWGMSAdditionalInfo,
                    SWGMSMain.internal_id==SWGMSAdditionalInfo.internal_id)
            results = db.session.execute(q_syn).all()
    
    return [r._asdict() for r in results]


def swg_monograph_search(search_type, search_value):
    base_q = db.select(SWGMain.dtxsid, SWGMain.name, SWGMain.casrn, SWGMain.inchikey,
                       SWGAdditionalInfo.spectrum_type, SWGAdditionalInfo.source, 
                       SWGAdditionalInfo.internal_id, SWGAdditionalInfo.link, SWGMain.record_type,
                       SWGAdditionalInfo.data_type, SWGAdditionalInfo.comment)
    
    if search_type == SearchType.InChIKey:
        q = base_q.filter(SWGMain.inchikey == search_value)
    elif search_type == SearchType.CASRN:
        q = base_q.filter(SWGMain.casrn==search_value)
    elif search_type == SearchType.CompoundName:
        q = base_q.filter(SWGMain.name.ilike(search_value))
    elif search_type == SearchType.DTXSID:
        q = base_q.filter(SWGMain.dtxsid==search_value)
    
    q = q.join_from(SWGMain, SWGAdditionalInfo,
                    SWGMain.internal_id==SWGAdditionalInfo.internal_id)
    
    results = db.session.execute(q).all()

    if (len(results) == 0) and (search_type == SearchType.CompoundName):
        q2 = db.select(Synonyms.dtxsid).filter(Synonyms.synonym.ilike(search_value))
        synonym_results = db.session.execute(q2).all()
        if len(synonym_results) > 0:
            synonym_dtxsid = synonym_results[0].dtxsid
            q_syn = base_q.filter(SWGMain.dtxsid==synonym_dtxsid).join_from(SWGMain, SWGAdditionalInfo,
                    SWGMain.internal_id==SWGAdditionalInfo.internal_id)
            results = db.session.execute(q_syn).all()

    return [r._asdict() for r in results]


def ecm_search(search_type, search_value):
    base_q = db.select(ECMMain.dtxsid, ECMMain.name, ECMMain.casrn, ECMMain.inchikey,
                       ECMAdditionalInfo.spectrum_type, ECMAdditionalInfo.source, 
                       ECMAdditionalInfo.internal_id, ECMAdditionalInfo.link, ECMMain.record_type,
                       ECMAdditionalInfo.data_type, ECMAdditionalInfo.comment)
    
    if search_type == SearchType.InChIKey:
        q = base_q.filter(ECMMain.inchikey == search_value)
    elif search_type == SearchType.CASRN:
        q = base_q.filter(ECMMain.casrn==search_value)
    elif search_type == SearchType.CompoundName:
        q = base_q.filter(ECMMain.name.ilike(search_value))
    elif search_type == SearchType.DTXSID:
        q = base_q.filter(ECMMain.dtxsid==search_value)
    
    q = q.join_from(ECMMain, ECMAdditionalInfo,
                    ECMMain.internal_id==ECMAdditionalInfo.internal_id)
    
    results = db.session.execute(q).all()

    if (len(results) == 0) and (search_type == SearchType.CompoundName):
        q2 = db.select(Synonyms.dtxsid).filter(Synonyms.synonym.ilike(search_value))
        synonym_results = db.session.execute(q2).all()
        if len(synonym_results) > 0:
            synonym_dtxsid = synonym_results[0].dtxsid
            q_syn = base_q.filter(ECMMain.dtxsid==synonym_dtxsid).join_from(ECMMain, ECMAdditionalInfo,
                    ECMMain.internal_id==ECMAdditionalInfo.internal_id)
            results = db.session.execute(q_syn).all()
    
    return [r._asdict() for r in results]


def agilent_search(search_type, search_value):
    base_q = db.select(AgilentMain.dtxsid, AgilentMain.name, AgilentMain.casrn, AgilentMain.inchikey,
                       AgilentAdditionalInfo.spectrum_type, AgilentAdditionalInfo.source, 
                       AgilentAdditionalInfo.internal_id, AgilentAdditionalInfo.link, AgilentMain.record_type,
                       AgilentAdditionalInfo.data_type, AgilentAdditionalInfo.comment)
    
    if search_type == SearchType.InChIKey:
        q = base_q.filter(AgilentMain.inchikey == search_value)
    elif search_type == SearchType.CASRN:
        q = base_q.filter(AgilentMain.casrn==search_value)
    elif search_type == SearchType.CompoundName:
        q = base_q.filter(AgilentMain.name.ilike(search_value))
    elif search_type == SearchType.DTXSID:
        q = base_q.filter(AgilentMain.dtxsid==search_value)
    
    q = q.join_from(AgilentMain, AgilentAdditionalInfo,
                    AgilentMain.internal_id==AgilentAdditionalInfo.internal_id)
    results = db.session.execute(q).all()

    if (len(results) == 0) and (search_type == SearchType.CompoundName):
        q2 = db.select(Synonyms.dtxsid).filter(Synonyms.synonym.ilike(search_value))
        synonym_results = db.session.execute(q2).all()
        if len(synonym_results) > 0:
            synonym_dtxsid = synonym_results[0].dtxsid
            q_syn = base_q.filter(AgilentMain.dtxsid==synonym_dtxsid).join_from(AgilentMain, AgilentAdditionalInfo,
                    AgilentMain.internal_id==AgilentAdditionalInfo.internal_id)
            results = db.session.execute(q_syn).all()
    
    return [r._asdict() for r in results]


def other_methods_search(search_type, search_value):
    base_q = db.select(OtherMethodsMain.dtxsid, OtherMethodsMain.name, OtherMethodsMain.casrn, OtherMethodsMain.inchikey,
                       OtherMethodsAdditionalInfo.spectrum_type, OtherMethodsAdditionalInfo.source, 
                       OtherMethodsAdditionalInfo.internal_id, OtherMethodsAdditionalInfo.link, OtherMethodsMain.record_type,
                       OtherMethodsAdditionalInfo.data_type, OtherMethodsAdditionalInfo.comment)
    
    if search_type == SearchType.InChIKey:
        q = base_q.filter(OtherMethodsMain.inchikey == search_value)
    elif search_type == SearchType.CASRN:
        q = base_q.filter(OtherMethodsMain.casrn==search_value)
    elif search_type == SearchType.CompoundName:
        q = base_q.filter(OtherMethodsMain.name.ilike(search_value))
    elif search_type == SearchType.DTXSID:
        q = base_q.filter(OtherMethodsMain.dtxsid==search_value)
    
    q = q.join_from(OtherMethodsMain, OtherMethodsAdditionalInfo,
                    OtherMethodsMain.internal_id==OtherMethodsAdditionalInfo.internal_id)
    results = db.session.execute(q).all()

    if (len(results) == 0) and (search_type == SearchType.CompoundName):
        q2 = db.select(Synonyms.dtxsid).filter(Synonyms.synonym.ilike(search_value))
        synonym_results = db.session.execute(q2).all()
        if len(synonym_results) > 0:
            synonym_dtxsid = synonym_results[0].dtxsid
            q_syn = base_q.filter(OtherMethodsMain.dtxsid==synonym_dtxsid).join_from(OtherMethodsMain, OtherMethodsAdditionalInfo,
                    OtherMethodsMain.internal_id==OtherMethodsAdditionalInfo.internal_id)
            results = db.session.execute(q_syn).all()
    
    return [r._asdict() for r in results]


@app.route("/monograph_list")
def monograph_list():
    from time import gmtime, strftime
    print("START: ", strftime("%H:%M:%S", gmtime()))
    filenames = []
    monograph_info = []

    ## info for CFSRE monographs
    q = db.select(CFSREMonographs.internal_id, CFSREMonographs.monograph_name, CFSREMonographs.year_published, CFSREMonographs.sub_source)
    results = db.session.execute(q).all()
    cfsre_filenames = [p.internal_id[:-4] for p in results]
    cfsre_monograph_info = []
    for r, fn in zip(results, cfsre_filenames):
        cfsre_monograph_info.append({"name":r.monograph_name, "year_published":r.year_published, "info_source":r.sub_source, "filename":fn, "source":"CFSRE", "internal_id":r.internal_id})
    filenames.extend(cfsre_filenames)
    monograph_info.extend(cfsre_monograph_info)

    ## info for SWG monographs
    q = db.select(SWGMonographs.internal_id, SWGMonographs.monograph_name, SWGMonographs.year_published, SWGMonographs.sub_source)
    results = db.session.execute(q).all()
    swg_filenames = [p.internal_id[:-4] for p in results]
    swg_monograph_info = []
    for r, fn in zip(results, swg_filenames):
        swg_monograph_info.append({"name":r.monograph_name, "year_published":r.year_published, "info_source":r.sub_source, "filename":fn, "source":"SWG", "internal_id":r.internal_id})
    filenames.extend(swg_filenames)
    monograph_info.extend(swg_monograph_info)
    
    return jsonify({"names": filenames, "monograph_info": monograph_info})


@app.route("/download/cfsre/<pdf_name>")
def download_cfsre(pdf_name):
    q = db.select(CFSREMonographs.pdf_data).filter(CFSREMonographs.internal_id==pdf_name)
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
    q = db.select(SWGMonographs.pdf_data).filter(SWGMonographs.internal_id==pdf_name)
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
    elif source == "SWG":
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
def get_pdf(source, internal_id):
    if source.lower() == "cfsre":
        q = db.select(CFSREMonographs.pdf_data).filter(CFSREMonographs.internal_id==internal_id)
    elif source == "ECM":
        q = db.select(ECMMethods.pdf_data).filter(ECMMethods.internal_id==internal_id)
    elif source == "SWG":
        q = db.select(SWGMonographs.pdf_data).filter(SWGMonographs.internal_id==internal_id)
    elif source == "Agilent":
        q = db.select(AgilentMethods.pdf_data).filter(AgilentMethods.internal_id==internal_id)
    else:
        q = db.select(OtherMethodsMethods.pdf_data).filter(OtherMethodsMethods.internal_id==internal_id)
    
    print(q)
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
def get_pdf_metadata(source, internal_id):
    if source == "ECM":
        q = db.select(ECMMethods.method_metadata, ECMMethods.method_name).filter(ECMMethods.internal_id==internal_id)
    elif source == "Agilent":
        q = db.select(AgilentMethods.method_metadata, AgilentMethods.method_name).filter(AgilentMethods.internal_id==internal_id)
    elif source == "CFSRE":
        q = db.select(CFSREMonographs.monograph_metadata, CFSREMonographs.monograph_name).filter(CFSREMonographs.internal_id==internal_id)
    elif source == "SWG":
        q = db.select(SWGMonographs.monograph_metadata, SWGMonographs.monograph_name).filter(SWGMonographs.internal_id==internal_id)
    else:
        q = db.select(OtherMethodsMethods.method_metadata, OtherMethodsMethods.method_name).filter(OtherMethodsMethods.internal_id==internal_id)
    
    data_row = db.session.execute(q).first()
    if data_row is not None:
        if source in ["CFSRE", "SWG"]:
            pdf_metadata = data_row.monograph_metadata
            pdf_name = data_row.monograph_name
        else:
            pdf_metadata = data_row.method_metadata
            pdf_name = data_row.method_name
        metadata_entries = pdf_metadata.split(";;")
        metadata_rows = [[x.split("::")[0], x.split("::")[1]] for x in metadata_entries]
        return jsonify({
            "pdf_name": pdf_name,
            "metadata_rows": metadata_rows
        })
    else:
        print("Error")
        return "Error: PDF name not found."
    

@app.route("/find_inchikeys/<inchikey>")
def find_inchikeys(inchikey):
    inchikey_first_block = inchikey[:14]
    all_inchikeys = []
    for x in [MonaMain, CFSREMain, SpectrabaseMain, MassbankMain, SWGMain, SWGMSMain, ECMMain, AgilentMain, OtherMethodsMain]:
        q = db.select(x.inchikey).filter(x.inchikey.like(inchikey_first_block+"%"))
        inchikeys = db.session.execute(q).all()
        inchikeys = [i.inchikey for i in inchikeys]
        all_inchikeys.extend(inchikeys)
    unique_inchikeys = set(all_inchikeys)
    return jsonify({
        "inchikey_present": inchikey in unique_inchikeys,
        "unique_inchikeys": sorted(list(unique_inchikeys))
    })

@app.route("/find_dtxsids/<source>/<internal_id>")
def find_dtxsids(source, internal_id):
    possible_sources = {
        "swg":SWGMain,
        "ecm":ECMMain,
        "cfsre":CFSREMain,
        "agilent":AgilentMain,
        "other":OtherMethodsMain
    }
    if source.lower() in possible_sources.keys():
        target_db = possible_sources[source.lower()]
        q = db.select(target_db.dtxsid).filter(target_db.internal_id==internal_id)
        dtxsids = db.session.execute(q).all()
        if len(dtxsids) > 0:
            dtxsids = [d[0] for d in dtxsids]
            q2 = db.select(IDTable.dtxsid, IDTable.casrn, IDTable.preferred_name).filter(IDTable.dtxsid.in_(dtxsids))
            chemical_ids = db.session.execute(q2).all()
            return jsonify({"chemical_ids":[c._asdict() for c in chemical_ids]})
        else:
            return f"Unknown error -- no DTXSIDs found for internal ID {internal_id} from source {source}"
    else:
        return f"Unidentified source '{source}'"

@app.route("/compound_similarity_search/<dtxsid>")
def find_similar_compounds(dtxsid, similarity_threshold=0.8):
    # Note: compound lists returned by this are sorted in decreasing order of
    # similarity, but the order of elements with the same similarity doesn't
    # appear to be guaranteed.
    if not re.match("^DTXSID[0-9]*$", dtxsid):
        return "Error: not a valid DTXSID."
    
    BASE_URL = "https://ccte-api-ccd-dev.epa.gov/similar-compound/by-dtxsid/"
    response = requests.get(f"{BASE_URL}{dtxsid}/{similarity_threshold}")
    if response.status_code == 200:
        return response.json()
    else:
        print("Error: ", response.status_code)
        return {}


@app.route("/get_similar_methods/<dtxsid>")
def get_similar_methods(dtxsid):
    similar_compounds_json = find_similar_compounds(dtxsid, similarity_threshold=0.5)
    similar_dtxsids = [sc["dtxsid"] for sc in similar_compounds_json]
    similarity_dict = {sc["dtxsid"]: sc["similarity"] for sc in similar_compounds_json}
    # add the actual DTXSID for now -- the case where there are methods for the DTXSID will likely be changed down the road
    similar_dtxsids.append(dtxsid)
    similarity_dict[dtxsid] = 1 
    # select all methods which have a dtxsid that is in the list
    # select all from main where dtxsid is in the list
    # desired fields: method name, source, year, similarity, dtxsid/compound name
    results = []
    table_tuples = [(ECMMain, ECMAdditionalInfo, ECMMethods), (AgilentMain, AgilentAdditionalInfo, AgilentMethods), (OtherMethodsMain, OtherMethodsAdditionalInfo, OtherMethodsMethods)]
    for search_table, additional_info, method_table in table_tuples:
        q = db.select(
                search_table.internal_id, search_table.dtxsid, additional_info.source,
                method_table.method_name, method_table.year_published
            ).filter(search_table.dtxsid.in_(similar_dtxsids)).join_from(search_table, additional_info, search_table.internal_id==additional_info.internal_id).join_from(search_table, method_table, search_table.internal_id==method_table.internal_id)
        similar_methods = [c._asdict() for c in db.session.execute(q).all()]
        results.extend(similar_methods)
    
    methods_with_searched_compound = [r["internal_id"] for r in results if r["dtxsid"] == dtxsid]
    dtxsid_names = get_names_for_dtxsids([r["dtxsid"] for r in results])

    internal_id_counts = Counter([r["internal_id"] for r in results])
    methods_with_multiple_compounds = [x for x in internal_id_counts.keys() if internal_id_counts[x] > 1]

    results = [{
            **r, "similarity": similarity_dict[r["dtxsid"]], "compound_name":dtxsid_names.get(r["dtxsid"]),
            "has_searched_compound": r["internal_id"] in methods_with_searched_compound,
            "dummy_id": r["internal_id"] if r["internal_id"] in methods_with_multiple_compounds else None
        } for r in results]
    ids_to_method_names = {r["internal_id"]:r["method_name"] for r in results}

    return jsonify({"results":results, "ids_to_method_names":ids_to_method_names})


def get_names_for_dtxsids(dtxsid_list):
    q = db.select(IDTable.preferred_name, IDTable.dtxsid).filter(IDTable.dtxsid.in_(dtxsid_list))
    results = [c._asdict() for c in db.session.execute(q).all()]
    names_for_dtxsids = {r["dtxsid"]:r["preferred_name"] for r in results}
    return names_for_dtxsids

@app.route("/methods_list")
def get_all_methods():
    table_tuples = [(AgilentMethods, AgilentAdditionalInfo), (ECMMethods, ECMAdditionalInfo), (OtherMethodsMethods, OtherMethodsAdditionalInfo)]
    results = []
    for methods, add_info in table_tuples:
        print(methods)
        q = db.select(methods.internal_id, methods.method_name, methods.method_number, methods.year_published,
                      methods.matrix, methods.analyte, add_info.source, add_info.spectrum_type,
                      add_info.comment).join_from(methods, add_info, methods.internal_id==add_info.internal_id)
        results.extend([c._asdict() for c in db.session.execute(q).all()])
    return jsonify({"results": results})


if __name__ == "__main__":
    db.init_app(app)
    app.run(host='0.0.0.0', port=5000)


