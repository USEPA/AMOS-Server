# Import Docker image
FROM ubuntu:20.04

# Put source code in docker container
WORKDIR /app
COPY . /app

#Need python3.9 to run random forest using multicores...
RUN apt-get update \
&& apt-get install -y software-properties-common libpq-dev \
&& add-apt-repository ppa:deadsnakes/ppa \
&& apt-get update \
&& apt install -y python3.12 python3.12-dev

# Install pip
#RUN echo Y  apt install python3-pip

COPY requirements.txt .
# Install dependencies
RUN pip install -r requirements.txt

# Expose port
EXPOSE 5000

# Run source code
CMD ["../usr/bin/python3", "app.py"]
