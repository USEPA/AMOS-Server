This is the backend for the Analytical Methods and Open Database (AMOS) project.  It performs the interactions between the frontend and a PostgreSQL database containing all of the records collected for the project, as well as providing additional enpoints for other applications to call as necessary.  It uses Flask for setting up endpoints that the app calls and SQLAlchemy for communicating with the database.

The deployed application can be found [here](https://ccte-cced-amos.epa.gov/).  The Vue-based frontend for this application can be found [here](https://github.com/USEPA/AMOS-UI).

Python 3.10.5 was used to develop this code.  The full list of Python packages used in this app can be found in requirements.txt. 
