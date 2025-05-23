from collections import defaultdict

import requests
from sqlalchemy import func

from table_definitions import db, AdditionalSources, AdditionalSubstanceInfo, \
    AnalyticalQC, ClassyFire, Contents, DatabaseSummary, FactSheets, \
    FunctionalUseClasses, MassSpectra, Methods, MethodsWithSpectra, RecordInfo, \
    SpectrumPDFs, SubstanceImages, Substances, Synonyms


EMPTY_ADDITIONAL_INFO_ROW = {"source_count": 0, "literature_count": 0, "patent_count": 0, "pubmed_count": 0}
PARTIAL_IDENTIFIER_SEARCH_FIELDS = [
    Substances.image_in_comptox, Substances.dtxsid, Substances.casrn, Substances.monoisotopic_mass,
    Substances.molecular_formula, Substances.preferred_name, AdditionalSubstanceInfo.pubmed_count,
    AdditionalSubstanceInfo.literature_count, AdditionalSubstanceInfo.patent_count
]


def additional_source_counts(dtxsids):
    """
    Pulls additional count data for a list of DTXSIDs.
    """
    query = db.select(AdditionalSubstanceInfo).filter(AdditionalSubstanceInfo.dtxsid.in_(dtxsids))
    results = [c[0].get_row_contents() for c in db.session.execute(query).all()]

    seen_dtxsids = set([r["dtxsid"] for r in results])
    missing_dtxsid_info = [{"dtxsid": d, "literature_count": 0, "patent_count": 0, "pubmed_count": 0, "source_count": 0} for d in dtxsids if d not in seen_dtxsids]
    return results + missing_dtxsid_info


def additional_sources_by_substance(dtxsid):
    """
    Retrieves links for supplemental sources (e.g., Wikipedia, ChemExpo) for a
    given DTXSID.
    """
    query = db.select(AdditionalSources).filter(AdditionalSources.dtxsid==dtxsid)
    return [c[0].get_row_contents() for c in db.session.execute(query).all()]


def classyfire_for_dtxsid(dtxsid, full_info=False):
    """
    Retrieves ClassyFire's classification info a given DTXSID.  By default this
    will only return the actual classification of the substance (kingdom,
    superclass, class, subclass), but all information can be returned by setting
    full_info to True.
    """
    search_fields = [ClassyFire.kingdom, ClassyFire.superklass, ClassyFire.klass, ClassyFire.subklass]
    if full_info:
        search_fields.extend([ClassyFire.direct_parent, ClassyFire.geometric_descriptor, ClassyFire.alternative_parents, ClassyFire.substituents])
    query = db.select(*search_fields).filter(ClassyFire.dtxsid==dtxsid)
    data_row = db.session.execute(query).first()
    if data_row is not None:
        return data_row._asdict()
    else:
        return None


def database_summary():
    """
    Retrieves the information from the database summary table.
    """
    query = db.select(DatabaseSummary)
    results = [c[0].get_row_contents() for c in db.session.execute(query).all()]
    result_dict = {r["field_name"]: r["info"] for r in results}
    return result_dict


def formula_search(formula):
    """
    Returns a list of substances which exactly match the given molecular formula.
    """
    query = db.select(Substances, AdditionalSubstanceInfo).join_from(Substances, AdditionalSubstanceInfo, Substances.dtxsid==AdditionalSubstanceInfo.dtxsid, isouter=True).filter(Substances.molecular_formula==formula)
    results = [r[0].get_row_contents() | (r[1].get_row_contents() if r[1] else EMPTY_ADDITIONAL_INFO_ROW) for r in db.session.execute(query).all()]
    return results


def functional_uses_for_dtxsids(dtxsid_list, include_substances_without_uses=True):
    """
    Retrieves lists of functional uses classes per DTXSID.  Substances without functional uses are
    given values of None by default, though this can be changed with the
    `include_substances_without_uses` flag.
    """
    query = db.select(FunctionalUseClasses).filter(FunctionalUseClasses.dtxsid.in_(dtxsid_list))
    results = [c[0].get_row_contents() for c in db.session.execute(query).all()]
    result_dict = {r["dtxsid"]: r["functional_classes"] for r in results}
    if include_substances_without_uses:
        for d in dtxsid_list:
            if d not in result_dict:
                result_dict[d] = None
    return result_dict
    


def ids_for_substances(dtxsids, record_type=None, additional_fields=[]):
    """
    Retrieves a list of record IDs that contain a given set of substances.
    """
    query = db.select(Contents.internal_id, *additional_fields).join_from(Contents, RecordInfo, Contents.internal_id==RecordInfo.internal_id).filter(Contents.dtxsid.in_(dtxsids)).distinct()
    if record_type is not None:
        query = query.filter(RecordInfo.record_type==record_type)
    results = [c._asdict() for c in db.session.execute(query).all()]
    return results


def inchikey_first_block_search(first_block):
    """
    Locates all substances where the first block of the InChIKey matches the searched first block.
    """
    query = db.select(Substances, AdditionalSubstanceInfo).join_from(Substances, AdditionalSubstanceInfo, Substances.dtxsid==AdditionalSubstanceInfo.dtxsid, isouter=True).filter(Substances.jchem_inchikey.like(first_block+"%") | Substances.indigo_inchikey.like(first_block+"%"))
    results = [r[0].get_row_contents() | (r[1].get_row_contents() if r[1] else EMPTY_ADDITIONAL_INFO_ROW) for r in db.session.execute(query).all()]
    return results


def mass_range_search(lower_mass_limit, upper_mass_limit):
    """
    Returns a list of substances whose monoisotopic mass is in the specified range.
    """
    query = db.select(Substances, AdditionalSubstanceInfo).join_from(Substances, AdditionalSubstanceInfo, Substances.dtxsid==AdditionalSubstanceInfo.dtxsid, isouter=True).filter(Substances.monoisotopic_mass.between(lower_mass_limit, upper_mass_limit))
    results = [r[0].get_row_contents() | (r[1].get_row_contents() if r[1] else EMPTY_ADDITIONAL_INFO_ROW) for r in db.session.execute(query).all()]
    return results


def mass_spectra_for_substances(dtxsid_list, ms_level=None, additional_fields=[]):
    """
    Takes a list of DTXSIDs and returns all mass spectra associated with those
    DTXSIDs.  Additional fields from the Contents, RecordInfo, and Spectrum
    tables can be added as needed.
    """
    query = db.select(Contents.dtxsid, RecordInfo.internal_id, RecordInfo.description, MassSpectra.spectrum, *additional_fields).filter(
        (Contents.dtxsid.in_(dtxsid_list)) & (RecordInfo.data_type=="Mass Spectrum")
    ).join_from(
        Contents, RecordInfo, Contents.internal_id==RecordInfo.internal_id
    ).join_from(
        Contents, MassSpectra, Contents.internal_id==MassSpectra.internal_id
    )
    if ms_level is not None:
        query = query.filter(MassSpectra.ms_level==ms_level)
    return [c._asdict() for c in db.session.execute(query).all()]


def mass_spectrum_search(lower_mass_limit, upper_mass_limit, methodology=None):
    """
    Retrieves basic information on a set of spectra from the database,
    constrained by a mass range and an analytical methodology.
    """
    query = db.select(
            Substances.dtxsid, Substances.preferred_name, Contents.internal_id, RecordInfo.description, RecordInfo.source, RecordInfo.link,
            MassSpectra.spectrum, MassSpectra.spectrum_metadata
        ).filter(
            Substances.monoisotopic_mass.between(lower_mass_limit, upper_mass_limit) & (RecordInfo.data_type=="Mass Spectrum")
        ).join_from(
            Substances, Contents, Substances.dtxsid==Contents.dtxsid
        ).join_from(
            Contents, RecordInfo, Contents.internal_id==RecordInfo.internal_id
        ).join_from(
            Contents, MassSpectra, Contents.internal_id==MassSpectra.internal_id
        )
    if methodology:
        query = query.filter(RecordInfo.methodologies.any(methodology))
    results = [c._asdict() for c in db.session.execute(query).all()]
    return results


def names_for_dtxsids(dtxsid_list):
    """
    Creates a dictionary that maps a list of DTXSIDs to the EPA-preferred name
    for the substance.
    """
    query = db.select(Substances.preferred_name, Substances.dtxsid).filter(Substances.dtxsid.in_(dtxsid_list))
    results = [c._asdict() for c in db.session.execute(query).all()]
    names_for_dtxsids = {r["dtxsid"]:r["preferred_name"] for r in results}
    return names_for_dtxsids


def pdf_by_id(internal_id, record_type):
    """
    Retrieves a PDF from the database based on its internal ID, with the record
    type indicating which table should be searched.  If no PDF is found, return
    None.
    """
    if record_type.lower() == "fact sheet":
        query = db.select(FactSheets.pdf_data).filter(FactSheets.internal_id==internal_id)
    elif record_type.lower() == "method":
        query = db.select(Methods.pdf_data).filter(Methods.internal_id==internal_id)
    elif record_type.lower() == "spectrum":
        if internal_id.startswith("AnalyticalQC-"):
            query = db.select(AnalyticalQC.pdf_data).filter(AnalyticalQC.internal_id==internal_id)
        else:
            query = db.select(SpectrumPDFs.pdf_data).filter(SpectrumPDFs.internal_id==internal_id)
    else:
        return f"Error: invalid record type {record_type}."
    
    data_row = db.session.execute(query).first()
    if data_row is not None:
        return data_row.pdf_data
    else:
        return None


def pdf_metadata(internal_id, record_type):
    """
    Single function for retrieving a PDF from the database along with the
    information that is always summoned alongside it -- metadata, a
    filename, and whether there are associated spectra.
    """
    if record_type == "method":
        query = db.select(Methods.method_name.label("pdf_name"), Methods.pdf_metadata, Methods.has_associated_spectra).filter(Methods.internal_id==internal_id)
    elif record_type == "fact sheet":
        query = db.select(FactSheets.fact_sheet_name.label("pdf_name"), FactSheets.pdf_metadata).filter(FactSheets.internal_id==internal_id)
    elif record_type == "spectrum":
        if internal_id.startswith("AnalyticalQC-"):
            query = db.select(AnalyticalQC.filename.label("pdf_name"), AnalyticalQC.pdf_metadata).filter(AnalyticalQC.internal_id==internal_id)
        else:
            query = db.select(SpectrumPDFs.internal_id.label("pdf_name"), SpectrumPDFs.pdf_metadata).filter(SpectrumPDFs.internal_id==internal_id)
    else:
        return {"error": f"Error: invalid record type {record_type}."}
    
    data_row = db.session.execute(query).first()
    if data_row is not None:
        data_row = data_row._asdict()
        return {
            "pdf_name": data_row["pdf_name"],
            "metadata_rows": data_row["pdf_metadata"],
            "has_associated_spectra": data_row.get("has_associated_spectra", False)
        }
    else:
        return None


def record_counts_by_dtxsid(dtxsid_list):
    """
    Gets counts of each type of record for each DTXSID in `dtxsid_list`.
    """
    query = db.select(
            Contents.dtxsid, RecordInfo.record_type, func.count(RecordInfo.internal_id)
        ).join_from(
            Contents, RecordInfo, Contents.internal_id==RecordInfo.internal_id
        ).filter(Contents.dtxsid.in_(dtxsid_list)).group_by(Contents.dtxsid, RecordInfo.record_type)
    results = [c._asdict() for c in db.session.execute(query).all()]
    result_dict = defaultdict(dict)
    for r in results:
        result_dict[r["dtxsid"]].update({r["record_type"]: r["count"]})
    return result_dict


def substance_counts_by_record(internal_id_list):
    """
    Gets counts of the number of substances in a list of internal IDs.
    """
    query = db.select(Contents.internal_id, func.count(Contents.dtxsid)).filter(Contents.internal_id.in_(internal_id_list)).group_by(Contents.internal_id)
    return [c._asdict() for c in db.session.execute(query).all()]


def substances_for_ids(internal_ids, additional_fields=[]):
    """
    Retrieves a deduplicated list of all substances that appear in a set of
    internal IDs, including common identifiers and a flag for image locaion. Can
    be either a single internal ID as a string or a list of IDs.
    """
    query = db.select(
            Contents.dtxsid, Substances.preferred_name, Substances.casrn, Substances.image_in_comptox, *additional_fields
        ).join_from(Contents, Substances, Contents.dtxsid==Substances.dtxsid)
    if type(internal_ids) == str:
        query = query.filter(Contents.internal_id==internal_ids)
    else:
        query = query.filter(Contents.internal_id.in_(internal_ids)).distinct()
    results = [c._asdict() for c in db.session.execute(query).all()]
    return results


def substring_search(substring):
    preferred_name_query = db.select(Substances, AdditionalSubstanceInfo).join_from(Substances, AdditionalSubstanceInfo, Substances.dtxsid==AdditionalSubstanceInfo.dtxsid, isouter=True).filter(Substances.preferred_name.ilike(f"%{substring}%"))
    synonym_query = db.select(Synonyms, Substances, AdditionalSubstanceInfo).join_from(
            Synonyms, Substances, Synonyms.dtxsid==Substances.dtxsid
        ).join_from(
            Substances, AdditionalSubstanceInfo, Substances.dtxsid==AdditionalSubstanceInfo.dtxsid, isouter=True
        ).filter(Synonyms.synonym.ilike(f"%{substring}%"))
    
    preferred_names = [r[0].get_row_contents() | (r[1].get_row_contents() if r[1] else EMPTY_ADDITIONAL_INFO_ROW) for r in db.session.execute(preferred_name_query).all()]
    synonyms = [r[0].get_row_contents() | r[1].get_row_contents() | (r[2].get_row_contents() if r[2] else EMPTY_ADDITIONAL_INFO_ROW) for r in db.session.execute(synonym_query).all()]
    return preferred_names, synonyms