# Import Docker image
FROM ubuntu:20.04

ARG DEBIAN_FRONTEND=noninteractive

# Put source code in docker container
WORKDIR /app
COPY . /app

#Need python3.9 to run random forest using multicores...
RUN apt-get update \
&& apt-get install -y software-properties-common build-essential libssl-dev libffi-dev libpq-dev curl \
&& add-apt-repository ppa:deadsnakes/ppa \
&& apt-get update \
&& apt-get install -y python3.12 python3.12-dev

RUN curl -sS https://bootstrap.pypa.io/get-pip.py | python3.12

RUN python3.12 -m pip install setuptools

COPY requirements.txt .

# Install dependencies
RUN python3.12 -m pip install -r requirements.txt

# Expose port
EXPOSE 5000

# Run source code
CMD ["python3.12", "app.py"]
