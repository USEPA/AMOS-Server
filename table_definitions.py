from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA


db = SQLAlchemy()


class Substances(db.Model):
    __tablename__ = "substances"
    __table_args__ = {'schema': 'amos'}
    dtxsid = db.Column(db.VARCHAR(32), primary_key=True)
    dtxcid = db.Column(db.VARCHAR(32))
    casrn = db.Column(db.VARCHAR(32))
    jchem_inchikey = db.Column(db.VARCHAR(27))
    indigo_inchikey = db.Column(db.VARCHAR(27))
    preferred_name = db.Column(db.TEXT)
    molecular_formula = db.Column(db.TEXT)
    monoisotopic_mass = db.Column(db.REAL)

    def get_row_contents(self):
        return {
            "dtxsid":self.dtxsid, "casrn":self.casrn, "jchem_inchikey":self.jchem_inchikey,
            "indigo_inchikey":self.indigo_inchikey, "preferred_name":self.preferred_name, 
            "molecular_formula":self.molecular_formula, "monoisotopic_mass":self.monoisotopic_mass
        }
    
class Synonyms(db.Model):
    __tablename__ = "synonyms"
    __table_args__ = {'schema': 'amos'}
    synonym = db.Column(db.TEXT, primary_key=True)
    dtxsid = db.Column(db.VARCHAR(32), primary_key=True)

class Contents(db.Model):
    __tablename__ = "contents"
    __table_args__ = {'schema': 'amos'}
    dtxsid = db.Column(db.VARCHAR(32), primary_key=True)
    internal_id = db.Column(db.TEXT, primary_key=True)


class RecordInfo(db.Model):
    __tablename__ = "record_info"
    __table_args__ = {'schema': 'amos'}
    internal_id = db.Column(db.TEXT, primary_key=True)
    methodologies = db.Column(ARRAY(db.VARCHAR(32)))
    source = db.Column(db.VARCHAR(64))
    link = db.Column(db.TEXT)
    experimental = db.Column(db.BOOLEAN)
    external_use_allowed = db.Column(db.BOOLEAN)
    description = db.Column(db.TEXT)
    data_type = db.Column(db.VARCHAR(32))
    record_type = db.Column(db.VARCHAR(32))

    def get_row_contents(self):
        return {
            "internal_id": self.internal_id, "methodologies": self.methodologies,
            "source": self.source, "link": self.link, "experimental": self.experimental,
            "external_use_allowed": self.external_use_allowed, "description": self.description,
            "data_type": self.data_type, "record_type": self.record_type
        }


class MassSpectra(db.Model):
    __tablename__ = "mass_spectra"
    __table_args__ = {'schema': 'amos'}
    internal_id = db.Column(db.TEXT, primary_key=True)
    splash = db.Column(db.VARCHAR(45))
    spectrum = db.Column(ARRAY(db.REAL, dimensions=2))
    spectral_entropy = db.Column(db.REAL)
    normalized_entropy = db.Column(db.REAL)
    has_associated_method = db.Column(db.BOOLEAN)
    spectrum_metadata = db.Column(db.JSON)


class SpectrumPDFs(db.Model):
    __tablename__ = "spectrum_pdfs"
    __table_args__ = {'schema': 'amos'}
    internal_id = db.Column(db.TEXT, primary_key=True)
    pdf_data = db.Column(BYTEA)
    pdf_metadata = db.Column(db.JSON)
    sub_source = db.Column(db.TEXT)
    date_published = db.Column(db.TEXT)


class FactSheets(db.Model):
    __tablename__ = "fact_sheets"
    __table_args__ = {'schema': 'amos'}
    internal_id = db.Column(db.TEXT, primary_key=True)
    pdf_data = db.Column(BYTEA)
    pdf_metadata = db.Column(db.JSON)
    sub_source = db.Column(db.TEXT)
    date_published = db.Column(db.TEXT)
    fact_sheet_name = db.Column(db.TEXT)
    document_type = db.Column(db.TEXT)
    analyte = db.Column(db.TEXT)


class Methods(db.Model):
    __tablename__ = "methods"
    __table_args__ = {'schema': 'amos'}
    internal_id = db.Column(db.TEXT, primary_key=True)
    pdf_data = db.Column(BYTEA)
    pdf_metadata = db.Column(db.JSON)
    date_published = db.Column(db.TEXT)
    method_name = db.Column(db.TEXT)
    method_number = db.Column(db.TEXT)
    analyte = db.Column(db.TEXT)
    chemical_class = db.Column(db.TEXT)
    matrix = db.Column(db.TEXT)
    has_associated_spectra = db.Column(db.BOOLEAN)
    document_type = db.Column(db.TEXT)
    publisher = db.Column(db.TEXT)


class MethodsWithSpectra(db.Model):
    __tablename__ = "methods_with_spectra"
    __table_args__ = {'schema': 'amos'}
    spectrum_id = db.Column(db.TEXT, primary_key=True)
    method_id = db.Column(db.TEXT)


class SubstanceImages(db.Model):
    __tablename__ = "substance_images"
    __table_args__ = {'schema': 'amos'}
    dtxsid = db.Column(db.TEXT, primary_key=True)
    png_image = db.Column(BYTEA)


class AnalyticalQC(db.Model):
    __tablename__ = "analytical_qc"
    __table_args__ = {'schema': 'amos'}
    internal_id = db.Column(db.TEXT, primary_key=True)
    pdf_data = db.Column(BYTEA)
    pdf_metadata = db.Column(db.JSON)
    filename = db.Column(db.TEXT)
    experiment_date = db.Column(db.TEXT)
    study = db.Column(db.TEXT)
    timepoint = db.Column(db.TEXT)
    batch = db.Column(db.TEXT)
    well = db.Column(db.TEXT)
    first_timepoint = db.Column(db.TEXT)
    last_timepoint = db.Column(db.TEXT)
    stability_call = db.Column(db.TEXT)
    tox21_id = db.Column(db.TEXT)
    ncgc_id = db.Column(db.TEXT)
    pubchem_sid = db.Column(db.TEXT)
    bottle_barcode = db.Column(db.TEXT)
    annotation = db.Column(db.TEXT)
    sample_id = db.Column(db.TEXT)


class DatabaseSummary(db.Model):
    __tablename__ = "database_summary"
    __table_args__ = {'schema': 'amos'}
    count_type = db.Column(db.VARCHAR(32), primary_key=True)
    subtype = db.Column(db.VARCHAR(32), primary_key=True)
    value_count = db.Column(db.INTEGER)

    def get_row_contents(self):
        return {
            "count_type": self.count_type, "subtype": self.subtype,
            "value_count": self.value_count
        }

class AdditionalSources(db.Model):
    __tablename__ = "additional_sources"
    __table_args__ = {'schema': 'amos'}
    dtxsid = db.Column(db.VARCHAR(32), primary_key=True)
    source_name = db.Column(db.TEXT, primary_key=True)
    link = db.Column(db.TEXT)
    description = db.Column(db.TEXT)

    def get_row_contents(self):
        return {
            "dtxsid": self.dtxsid, "source_name": self.source_name, 
            "link": self.link, "description": self.description
        }


class NMRSpectra(db.Model):
    __tablename__ = "nmr_spectra"
    __table_args__ = {'schema': 'amos'}
    internal_id = db.Column(db.TEXT, primary_key=True)
    frequency = db.Column(db.REAL)
    nucleus = db.Column(db.VARCHAR(16))
    solvent = db.Column(db.TEXT)
    temperature = db.Column(db.REAL)
    coupling_constants = db.Column(db.JSON)
    first_x = db.Column(db.REAL)
    last_x = db.Column(db.REAL)
    x_units = db.Column(db.VARCHAR(16))
    intensities = db.Column(ARRAY(db.REAL, dimensions=1))
    spectrum_metadata = db.Column(db.JSON)