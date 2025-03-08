FROM python:3.12-alpine

RUN apk add --update alpine-sdk

WORKDIR /app

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "app.py"]
