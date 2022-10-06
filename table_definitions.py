"""
Gregory Janesch

Description: This file contains the definitions of all of the SQLite database
tables that are used in the app.  Each database has a bind key to go with it --
the default key is currently reserved for a unified database that is currently
not being created.  There is a database for each data source and one for the ID
tables.
"""

from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()

#######################################################################
########## TABLES FOR MONA ############################################
#######################################################################

class MonaMain(db.Model):
    __tablename__ = "mona_main"
    __bind_key__ = "mona"
    internal_id = db.Column(db.Text, primary_key=True)
    name = db.Column(db.Text)
    cas_number = db.Column(db.Text)
    dtxsid = db.Column(db.Text)
    inchikey = db.Column(db.String(27))
    record_type = db.Column(db.Text)


class MonaAdditionalInfo(db.Model):
    __tablename__ = "mona_additional_info"
    __bind_key__ = "mona"
    internal_id = db.Column(db.Text, primary_key=True)
    spectrum_type = db.Column(db.Text)
    source = db.Column(db.Text)
    link = db.Column(db.Text)
    experimental = db.Column(db.Boolean)
    comment = db.Column(db.Text)
    data_type = db.Column(db.Text)


class MonaSpectra(db.Model):
    __tablename__ = "mona_spectra"
    __bind_key__ = "mona"
    internal_id = db.Column(db.Text, primary_key=True)
    splash = db.Column(db.String(45))
    spectrum = db.Column(db.Text)
    spectral_entropy = db.Column(db.Float)
    normalized_entropy = db.Column(db.Float)


#######################################################################
########## TABLES FOR CFSRE ###########################################
#######################################################################

class CFSREMain(db.Model):
    __tablename__ = "cfsre_main"
    __bind_key__ = "cfsre"
    internal_id = db.Column(db.Text, primary_key=True)
    name = db.Column(db.Text)
    cas_number = db.Column(db.Text)
    dtxsid = db.Column(db.Text, primary_key=True)
    inchikey = db.Column(db.String(27))
    record_type = db.Column(db.Text)


class CFSREAdditionalInfo(db.Model):
    __tablename__ = "cfsre_additional_info"
    __bind_key__ = "cfsre"
    internal_id = db.Column(db.Text, primary_key=True)
    spectrum_type = db.Column(db.Text, primary_key=True)
    source = db.Column(db.Text)
    link = db.Column(db.Text)
    experimental = db.Column(db.Boolean)
    comment = db.Column(db.Text)
    data_type = db.Column(db.Text)


class CFSREMonographs(db.Model):
    __tablename__ = "cfsre_monographs"
    __bind_key__ = "cfsre"
    internal_id = db.Column(db.Text, primary_key=True)
    pdf_data = db.Column(db.LargeBinary)
    year_published = db.Column(db.Integer)
    monograph_metadata = db.Column(db.Text)
    monograph_name = db.Column(db.Text)
    sub_source = db.Column(db.Text)

#######################################################################
########## TABLES FOR SPECTRABASE #####################################
#######################################################################

class SpectrabaseMain(db.Model):
    __tablename__ = "spectrabase_main"
    __bind_key__ = "spectrabase"
    internal_id = db.Column(db.Text, primary_key=True)
    name = db.Column(db.Text)
    cas_number = db.Column(db.Text)
    dtxsid = db.Column(db.Text)
    inchikey = db.Column(db.String(27))
    record_type = db.Column(db.Text)


class SpectrabaseAdditionalInfo(db.Model):
    __tablename__ = "spectrabase_additional_info"
    __bind_key__ = "spectrabase"
    internal_id = db.Column(db.Text, primary_key=True)
    spectrum_type = db.Column(db.Text)
    source = db.Column(db.Text)
    link = db.Column(db.Text)
    experimental = db.Column(db.Boolean)
    comment = db.Column(db.Text)
    data_type = db.Column(db.Text)


#######################################################################
########## TABLES FOR MASSBANK EU #####################################
#######################################################################

class MassbankMain(db.Model):
    __tablename__ = "massbank_main"
    __bind_key__ = "massbank"
    internal_id = db.Column(db.Text, primary_key=True)
    name = db.Column(db.String(27))
    cas_number = db.Column(db.Text)
    dtxsid = db.Column(db.Text)
    inchikey = db.Column(db.Text)
    record_type = db.Column(db.Text)


class MassbankAdditionalInfo(db.Model):
    __tablename__ = "massbank_additional_info"
    __bind_key__ = "massbank"
    internal_id = db.Column(db.Text, primary_key=True)
    spectrum_type = db.Column(db.Text)
    source = db.Column(db.Text)
    link = db.Column(db.Text)
    experimental = db.Column(db.Boolean)
    comment = db.Column(db.Text)
    data_type = db.Column(db.Text)


class MassbankSpectra(db.Model):
    __tablename__ = "massbank_spectra"
    __bind_key__ = "massbank"
    internal_id = db.Column(db.Text, primary_key=True)
    splash = db.Column(db.String(45))
    spectrum = db.Column(db.Text)
    spectral_entropy = db.Column(db.Float)
    normalized_entropy = db.Column(db.Float)


#######################################################################
########## TABLES FOR SWG MONOGRAPHS ##################################
#######################################################################

class SWGMain(db.Model):
    __tablename__ = "swg_main"
    __bind_key__ = "swg_mono"
    internal_id = db.Column(db.Text, primary_key=True)
    name = db.Column(db.Text)
    cas_number = db.Column(db.Text)
    dtxsid = db.Column(db.Text)
    inchikey = db.Column(db.String(27))
    record_type = db.Column(db.Text)


class SWGAdditionalInfo(db.Model):
    __tablename__ = "swg_additional_info"
    __bind_key__ = "swg_mono"
    internal_id = db.Column(db.Text, primary_key=True)
    spectrum_type = db.Column(db.Text)
    source = db.Column(db.Text)
    link = db.Column(db.Text)
    experimental = db.Column(db.Boolean)
    comment = db.Column(db.Text)
    data_type = db.Column(db.Text)


class SWGMonographs(db.Model):
    __tablename__ = "swg_monographs"
    __bind_key__ = "swg_mono"
    internal_id = db.Column(db.Text, primary_key=True)
    pdf_data = db.Column(db.LargeBinary)
    year_published = db.Column(db.Integer)
    monograph_metadata = db.Column(db.Text)
    monograph_name = db.Column(db.Text)
    sub_source = db.Column(db.Text)


#######################################################################
########## TABLES FOR SWG MASS SPECTRA ################################
#######################################################################

class SWGMSMain(db.Model):
    __tablename__ = "swg_ms_main"
    __bind_key__ = "swg_ms"
    internal_id = db.Column(db.Text, primary_key=True)
    name = db.Column(db.Text)
    cas_number = db.Column(db.Text)
    dtxsid = db.Column(db.Text)
    inchikey = db.Column(db.String(27))
    record_type = db.Column(db.Text)


class SWGMSAdditionalInfo(db.Model):
    __tablename__ = "swg_ms_additional_info"
    __bind_key__ = "swg_ms"
    internal_id = db.Column(db.Text, primary_key=True)
    spectrum_type = db.Column(db.Text)
    source = db.Column(db.Text)
    link = db.Column(db.Text)
    experimental = db.Column(db.Boolean)
    comment = db.Column(db.Text)
    data_type = db.Column(db.Text)

    
class SWGMSSpectra(db.Model):
    __tablename__ = "swg_ms_spectra"
    __bind_key__ = "swg_ms"
    internal_id = db.Column(db.Text, primary_key=True)
    splash = db.Column(db.Text)
    spectrum = db.Column(db.Text)
    spectral_entropy = db.Column(db.Float)
    normalized_entropy = db.Column(db.Float)


#######################################################################
########## TABLES FOR ECM #############################################
#######################################################################

class ECMMain(db.Model):
    __tablename__ = "ecm_main"
    __bind_key__ = "ecm"
    internal_id = db.Column(db.Text, primary_key=True)
    name = db.Column(db.Text, primary_key=True)
    cas_number = db.Column(db.Text)
    dtxsid = db.Column(db.Text)
    inchikey = db.Column(db.String(27))
    record_type = db.Column(db.Text)


class ECMAdditionalInfo(db.Model):
    __tablename__ = "ecm_additional_info"
    __bind_key__ = "ecm"
    internal_id = db.Column(db.Text, primary_key=True)
    spectrum_type = db.Column(db.Text)
    source = db.Column(db.Text)
    link = db.Column(db.Text)
    experimental = db.Column(db.Boolean)
    comment = db.Column(db.Text)
    data_type = db.Column(db.Text)


class ECMMethods(db.Model):
    __tablename__ = "ecm_methods"
    __bind_key__ = "ecm"
    internal_id = db.Column(db.Text, primary_key=True)
    pdf_data = db.Column(db.LargeBinary)
    method_name = db.Column(db.Text)
    internal_only = db.Column(db.Boolean)
    year_published = db.Column(db.Integer)
    method_metadata = db.Column(db.Text)


#######################################################################
########## TABLES FOR AGILENT INFO ####################################
#######################################################################

class AgilentMain(db.Model):
    __tablename__ = "agilent_main"
    __bind_key__ = "agilent"
    internal_id = db.Column(db.Text, primary_key=True)
    name = db.Column(db.Text)
    cas_number = db.Column(db.Text)
    dtxsid = db.Column(db.Text, primary_key=True)
    inchikey = db.Column(db.String(27))
    record_type = db.Column(db.Text)


class AgilentAdditionalInfo(db.Model):
    __tablename__ = "agilent_additional_info"
    __bind_key__ = "agilent"
    internal_id = db.Column(db.Text, primary_key=True)
    spectrum_type = db.Column(db.Text)
    source = db.Column(db.Text)
    link = db.Column(db.Text)
    experimental = db.Column(db.Boolean)
    comment = db.Column(db.Text)
    data_type = db.Column(db.Text)


class AgilentMethods(db.Model):
    __tablename__ = "agilent_methods"
    __bind_key__ = "agilent"
    internal_id = db.Column(db.Text, primary_key=True)
    pdf_data = db.Column(db.LargeBinary)
    method_name = db.Column(db.Text)
    internal_only = db.Column(db.Boolean)
    year_published = db.Column(db.Integer)
    method_metadata = db.Column(db.Text)



#######################################################################
########## TABLES FOR OTHER METHODS ###################################
#######################################################################

class OtherMethodsMain(db.Model):
    __tablename__ = "other_methods_main"
    __bind_key__ = "other_methods"
    internal_id = db.Column(db.Text, primary_key=True)
    name = db.Column(db.Text)
    cas_number = db.Column(db.Text)
    dtxsid = db.Column(db.Text, primary_key=True)
    inchikey = db.Column(db.String(27))
    record_type = db.Column(db.Text)


class OtherMethodsAdditionalInfo(db.Model):
    __tablename__ = "other_methods_additional_info"
    __bind_key__ = "other_methods"
    internal_id = db.Column(db.Text, primary_key=True)
    spectrum_type = db.Column(db.Text)
    source = db.Column(db.Text)
    link = db.Column(db.Text)
    experimental = db.Column(db.Boolean)
    comment = db.Column(db.Text)
    data_type = db.Column(db.Text)


class OtherMethodsMethods(db.Model):
    __tablename__ = "other_methods_methods"
    __bind_key__ = "other_methods"
    internal_id = db.Column(db.Text, primary_key=True)
    pdf_data = db.Column(db.LargeBinary)
    method_name = db.Column(db.Text)
    internal_only = db.Column(db.Boolean)
    year_published = db.Column(db.Integer)
    method_metadata = db.Column(db.Text)



#######################################################################
########## TABLES FOR ID INFO #########################################
#######################################################################

class IDTable(db.Model):
    __tablename__ = "ids"
    #__bind_key__ = "master_db"
    id = db.Column(db.Integer, primary_key=True)
    dtxsid = db.Column(db.Text)
    casrn = db.Column(db.Text)
    inchikey = db.Column(db.String(27))
    preferred_name = db.Column(db.Text)
    molecular_formula = db.Column(db.Text)
    molecular_weight = db.Column(db.Float)