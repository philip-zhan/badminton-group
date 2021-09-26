# Badminton Group Tool

## Prerequisites

- [Python3](https://www.python.org/downloads/) (currently tested with version 3.9.5)
- [gcloud tool](https://cloud.google.com/sdk/docs/install)
- `badminton-group-b8b954f5e8cf.json` file containing database secrets. Ask the maintainer for it if you think you need it.

## Run Locally

1. Run `pip install -r requirements.txt` if it's been changed since the last time you ran it
2. Run `run.sh` to start a local server

## Deploy

1. Run `deploy.sh` to deploy it to Google App Engine if you're authorized to do so

## Useful Resources

- [GCP Console](https://console.cloud.google.com/home/dashboard?project=badminton-group)
- [Quickstart for Python 3 in the App Engine Standard Environment](https://cloud.google.com/appengine/docs/standard/python3/quickstart)
