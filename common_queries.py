from collections import defaultdict

from sqlalchemy import func

from table_definitions import db, AnalyticalQC, Contents, FactSheets, \
    Methods, MethodsWithSpectra, RecordInfo, SpectrumData, \
    SpectrumPDFs,SubstanceImages, Substances,  Synonyms


def get_spectra_for_substances(dtxsid_list, additional_fields=[]):
    """
    Takes a list of DTXSIDs and returns all spectra associated with those
    DTXSIDs.  Additional fields from the Contents, RecordInfo, and Spectrum
    tables can be added as needed.
    """
    q = db.select(Contents.dtxsid, RecordInfo.internal_id, RecordInfo.description, SpectrumData.spectrum, *additional_fields).filter(
        (Contents.dtxsid.in_(dtxsid_list)) & (RecordInfo.data_type == "Spectrum")
    ).join_from(
        Contents, RecordInfo, Contents.internal_id==RecordInfo.internal_id
    ).join_from(
        Contents, SpectrumData, Contents.internal_id==SpectrumData.internal_id
    )
    return [c._asdict() for c in db.session.execute(q).all()]


def names_for_dtxsids(dtxsid_list):
    """
    Creates a dictionary that maps a list of DTXSIDs to the EPA-preferred name
    for the substance.
    """
    query = db.select(Substances.preferred_name, Substances.dtxsid).filter(Substances.dtxsid.in_(dtxsid_list))
    results = [c._asdict() for c in db.session.execute(query).all()]
    names_for_dtxsids = {r["dtxsid"]:r["preferred_name"] for r in results}
    return names_for_dtxsids


def pdf_with_info(internal_id, record_type):
    """
    Single function for retrieving a PDF from the database along with the
    information that is always summoned alongside it -- metadata, a
    filename, and whether there are associated spectra.
    """
    if record_type == "method":
        query = db.select(Methods.pdf_data, Methods.method_name.label("pdf_name"), Methods.pdf_metadata, Methods.has_associated_spectra).filter(Methods.internal_id==internal_id)
    elif record_type == "fact sheet":
        query = db.select(FactSheets.pdf_data, FactSheets.fact_sheet_name.label("pdf_name"), FactSheets.pdf_metadata).filter(FactSheets.internal_id==internal_id)
    elif record_type == "spectrum":
        query = db.select(AnalyticalQC.pdf_data, AnalyticalQC.filename.label("pdf_name"), AnalyticalQC.pdf_metadata).filter(AnalyticalQC.internal_id==internal_id)
    else:
        return {"error": f"Error: invalid record type {record_type}."}
    
    data_row = db.session.execute(query).first()
    if data_row is not None:
        data_row = data_row._asdict()
        return {
            "pdf_data": data_row["pdf_data"],
            "pdf_name": data_row["pdf_name"],
            "metadata_rows": data_row["pdf_metadata"],
            "has_associated_spectra": data_row.get("has_associated_spectra", False)
        }
    else:
        return {"error": f"Error: no PDF found for internal ID '{internal_id}'."}


def record_counts_by_dtxsid(dtxsid_list):
    """
    Gets counts of each type of record for each DTXSID in `dtxsid_list`.
    """
    query = db.select(Contents.dtxsid, RecordInfo.record_type, func.count(RecordInfo.internal_id)).join_from(Contents, RecordInfo, Contents.internal_id==RecordInfo.internal_id).filter(Contents.dtxsid.in_(dtxsid_list)).group_by(Contents.dtxsid, RecordInfo.record_type)
    results = [c._asdict() for c in db.session.execute(query).all()]
    result_dict = defaultdict(dict)
    for r in results:
        result_dict[r["dtxsid"]].update({r["record_type"]: r["count"]})
    return result_dict


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


def substances_for_ids(internal_ids, additional_fields=[]):
    query = db.select(
            Contents.dtxsid, Substances.preferred_name, Substances.casrn, *additional_fields
        ).join_from(Contents, Substances, Contents.dtxsid==Substances.dtxsid)
    if type(internal_ids) == str:
        query = query.filter(Contents.internal_id==internal_ids)
    else:
        query = query.filter(Contents.internal_id.in_(internal_ids)).distinct()
    results = [c._asdict() for c in db.session.execute(query).all()]
    return results