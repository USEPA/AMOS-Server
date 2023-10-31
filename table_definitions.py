from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import ARRAY, BYTEA


db = SQLAlchemy()


class Compounds(db.Model):
    __tablename__ = "compounds"
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


class SpectrumData(db.Model):
    __tablename__ = "spectrum_data"
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


class MethodsWithSpectra(db.Model):
    __tablename__ = "methods_with_spectra"
    __table_args__ = {'schema': 'amos'}
    spectrum_id = db.Column(db.TEXT, primary_key=True)
    method_id = db.Column(db.TEXT)


class CompoundImages(db.Model):
    __tablename__ = "compound_images"
    __table_args__ = {'schema': 'amos'}
    dtxsid = db.Column(db.TEXT, primary_key=True)
    png_image = db.Column(BYTEA)