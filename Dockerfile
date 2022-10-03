# Import Docker image
FROM ubuntu20.04

# Put source code in docker container
WORKDIR app
COPY . app

#Need python3.9 to run random forest using multicores...
RUN apt-get update
RUN apt-get install -y python3.9
RUN apt-get install -y python3-pip
RUN apt-get install -y python3-tk

# Install pip
#RUN echo Y  apt install python3-pip

COPY requirements.txt .
# Install dependencies
RUN pip install -r requirements.txt

# Expose port
EXPOSE 5000

# Run source code
CMD [..usrbinpython3, app.py]