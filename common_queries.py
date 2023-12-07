from collections import defaultdict

from sqlalchemy import func

from table_definitions import db, Contents, FactSheets, Methods, \
    MethodsWithSpectra, RecordInfo, SpectrumData, SpectrumPDFs, \
    SubstanceImages, Substances,  Synonyms


def names_for_dtxsids(dtxsid_list):
    """
    Creates a dictionary that maps a list of DTXSIDs to the EPA-preferred name
    for the substance.
    """
    query = db.select(Substances.preferred_name, Substances.dtxsid).filter(Substances.dtxsid.in_(dtxsid_list))
    results = [c._asdict() for c in db.session.execute(query).all()]
    names_for_dtxsids = {r["dtxsid"]:r["preferred_name"] for r in results}
    return names_for_dtxsids


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