This is the backend used to handle the search app's interactions with a PostgreSQL database containing the spectra, monographs, and methods that the search app works with.  It uses Flask for setting up endpoints that the app calls and SQLAlchemy for communicating with the database.

The Vue-based frontend for this application can be found [here](https://ccte-bitbucket.epa.gov/users/gjanesch/repos/spectrum-search-app-client/browse).

Python 3.10.5 was used to develop this code.  The full list of Python packages used in this app can be found in requirements.txt. 
