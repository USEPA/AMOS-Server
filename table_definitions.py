from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA


db = SQLAlchemy()


class Compounds(db.Model):
    __tablename__ = "compounds"
    __table_args__ = {'schema': 'spectrum_db'}
    dtxsid = db.Column(db.VARCHAR(32), primary_key=True)
    casrn = db.Column(db.VARCHAR(32))
    inchikey = db.Column(db.VARCHAR(27))
    preferred_name = db.Column(db.TEXT)
    compound_image = db.Column(BYTEA)
    molecular_formula = db.Column(db.TEXT)
    molecular_weight = db.Column(db.REAL)
    num_spectra = db.Column(db.INTEGER)
    num_monographs = db.Column(db.INTEGER)
    num_methods = db.Column(db.INTEGER)

    def get_row_contents(self):
        return {
            "dtxsid":self.dtxsid, "casrn":self.casrn, "inchikey":self.inchikey, "preferred_name":self.preferred_name, 
            "compound_image":self.compound_image, "molecular_formula":self.molecular_formula, "molecular_weight":self.molecular_weight,
            "num_spectra":self.num_spectra, "num_monographs":self.num_monographs, "num_methods":self.num_methods
        }
    
class Synonyms(db.Model):
    __tablename__ = "synonyms"
    __table_args__ = {'schema': 'spectrum_db'}
    synonym = db.Column(db.TEXT, primary_key=True)
    dtxsid = db.Column(db.VARCHAR(32))

class Contents(db.Model):
    __tablename__ = "contents"
    __table_args__ = {'schema': 'spectrum_db'}
    dtxsid = db.Column(db.VARCHAR(32), primary_key=True)
    internal_id = db.Column(db.TEXT, primary_key=True)


class RecordInfo(db.Model):
    __tablename__ = "record_info"
    __table_args__ = {'schema': 'spectrum_db'}
    internal_id = db.Column(db.TEXT, primary_key=True)
    spectrum_types = db.Column(ARRAY(db.VARCHAR(32)))
    source = db.Column(db.VARCHAR(64))
    link = db.Column(db.TEXT)
    experimental = db.Column(db.BOOLEAN)
    external_use_allowed = db.Column(db.BOOLEAN)
    description = db.Column(db.TEXT)
    data_type = db.Column(db.VARCHAR(32))
    record_type = db.Column(db.VARCHAR(32))


class SpectrumData(db.Model):
    __tablename__ = "spectrum_data"
    __table_args__ = {'schema': 'spectrum_db'}
    internal_id = db.Column(db.TEXT, primary_key=True)
    splash = db.Column(db.VARCHAR(45))
    spectrum = db.Column(ARRAY(db.REAL, dimensions=2))
    spectral_entropy = db.Column(db.REAL)
    normalized_entropy = db.Column(db.REAL)


class SpectrumPDFs(db.Model):
    __tablename__ = "spectrum_pdfs"
    __table_args__ = {'schema': 'spectrum_db'}
    internal_id = db.Column(db.TEXT, primary_key=True)
    pdf_data = db.Column(BYTEA)
    pdf_metadata = db.Column(db.JSON)
    sub_source = db.Column(db.TEXT)
    date_published = db.Column(db.TEXT)
    external_use_allowed = db.Column(db.BOOLEAN)


class Monographs(db.Model):
    __tablename__ = "monographs"
    __table_args__ = {'schema': 'spectrum_db'}
    internal_id = db.Column(db.TEXT, primary_key=True)
    pdf_data = db.Column(BYTEA)
    pdf_metadata = db.Column(db.JSON)
    sub_source = db.Column(db.TEXT)
    date_published = db.Column(db.TEXT)
    monograph_name = db.Column(db.TEXT)


class Methods(db.Model):
    __tablename__ = "methods"
    __table_args__ = {'schema': 'spectrum_db'}
    internal_id = db.Column(db.TEXT, primary_key=True)
    pdf_data = db.Column(BYTEA)
    pdf_metadata = db.Column(db.JSON)
    sub_source = db.Column(db.TEXT)
    date_published = db.Column(db.TEXT)
    method_name = db.Column(db.TEXT)
    method_number = db.Column(db.TEXT)
    analyte = db.Column(db.TEXT)
    matrix = db.Column(db.TEXT)