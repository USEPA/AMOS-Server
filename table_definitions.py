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
    image_in_comptox = db.Column(db.BOOLEAN)
    smiles = db.Column(db.TEXT)

    def get_row_contents(self):
        return {
            "dtxsid": self.dtxsid, "dtxcid": self.dtxcid, "casrn": self.casrn,
            "jchem_inchikey": self.jchem_inchikey, "indigo_inchikey": self.indigo_inchikey,
            "preferred_name":self.preferred_name, "molecular_formula": self.molecular_formula,
            "monoisotopic_mass": self.monoisotopic_mass, "image_in_comptox": self.image_in_comptox,
            "smiles": self.smiles
        }


class Synonyms(db.Model):
    __tablename__ = "synonyms"
    __table_args__ = {'schema': 'amos'}
    synonym = db.Column(db.TEXT, primary_key=True)
    dtxsid = db.Column(db.VARCHAR(32), primary_key=True)

    def get_row_contents(self):
        return {"dtxsid": self.dtxsid, "synonym": self.synonym}


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
    ms_level = db.Column(db.INTEGER)


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
    functional_classes = db.Column(db.TEXT)


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
    mmdb_matrix = db.Column(db.TEXT)


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
    flags = db.Column(db.TEXT)
    lcms_amen_pos_true = db.Column(db.INTEGER)
    lcms_amen_neg_true = db.Column(db.INTEGER)


class DatabaseSummary(db.Model):
    __tablename__ = "database_summary"
    __table_args__ = {'schema': 'amos'}
    field_name = db.Column(db.VARCHAR(32), primary_key=True)
    info = db.Column(db.JSON)

    def get_row_contents(self):
        return {"field_name": self.field_name, "info": self.info}


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
    splash = db.Column(db.VARCHAR(45))


class ClassyFire(db.Model):
    __tablename__ = "classyfire"
    __table_args__ = {'schema': 'amos'}
    dtxsid = db.Column(db.VARCHAR(32), primary_key=True)
    kingdom = db.Column(db.TEXT)
    superklass = db.Column(db.TEXT)
    klass = db.Column(db.TEXT)
    subklass = db.Column(db.TEXT)
    direct_parent = db.Column(db.TEXT)
    geometric_descriptor = db.Column(db.TEXT)
    alternative_parents = db.Column(ARRAY(db.TEXT, dimensions=1))
    substituents = db.Column(ARRAY(db.TEXT, dimensions=1))


class FunctionalUseClasses(db.Model):
    __tablename__ = "functional_use_classes"
    __table_args__ = {'schema': 'amos'}
    dtxsid = db.Column(db.VARCHAR(32), primary_key=True)
    functional_classes = db.Column(ARRAY(db.TEXT, dimensions=1))


class DataSourceInfo(db.Model):
    __tablename__ = "data_source_info"
    __table_args__ = {'schema': 'amos'}
    full_name = db.Column(db.TEXT, primary_key=True)
    source_ids = db.Column(ARRAY(db.TEXT, dimensions=1))
    category = db.Column(db.TEXT)
    description = db.Column(db.TEXT)
    url = db.Column(db.TEXT)
    substances = db.Column(db.INTEGER)
    fact_sheets = db.Column(db.INTEGER)
    methods = db.Column(db.INTEGER)
    spectra = db.Column(db.INTEGER)

    def get_row_contents(self):
        return {
            "full_name": self.full_name, "source_ids": self.source_ids, "category": self.category,
            "description": self.description, "url": self.url, "substances": self.substances,
            "fact_sheets": self.fact_sheets, "methods": self.methods, "spectra": self.spectra
        }


class InfraredSpectra(db.Model):
    __tablename__ = "infrared_spectra"
    __table_args__ = {'schema': 'amos'}
    internal_id = db.Column(db.TEXT, primary_key=True)
    ir_type = db.Column(db.VARCHAR(16))
    laser_frequency = db.Column(db.REAL)
    first_x = db.Column(db.REAL)
    last_x = db.Column(db.REAL)
    intensities = db.Column(ARRAY(db.REAL, dimensions=1))
    spectrum_metadata = db.Column(db.JSON)


class AdditionalSubstanceInfo(db.Model):
    __tablename__ = "additional_substance_info"
    __table_args__ = {'schema': 'amos'}
    dtxsid = db.Column(db.VARCHAR(32), primary_key=True)
    source_count = db.Column(db.INTEGER)
    patent_count = db.Column(db.INTEGER)
    literature_count = db.Column(db.INTEGER)
    pubmed_count = db.Column(db.INTEGER)

    def get_row_contents(self):
        return {
            "dtxsid": self.dtxsid, "source_count": self.source_count, "patent_count": self.patent_count,
            "literature_count": self.literature_count, "pubmed_count": self.pubmed_count 
        }