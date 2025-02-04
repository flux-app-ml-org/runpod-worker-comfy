# runpod-worker-comfy

Original repo `https://github.com/blib-la/runpod-worker-comfy`

# Development

1. Install [pyenv](https://github.com/pyenv/pyenv)
2. Create virtualenv and activate
```bash
pyenv virtualenv venv
pyenv activate venv

pip install -r requirements.txt # install deps
sudo apt-get update && sudo apt-get install -y libssl-dev libffi-dev python3-dev

pyenv install 3.11
pyenv local 3.11
source ~/.bashrc # reload terminal

pip install aiohttp
pip intsall -r requirements.txt
```

# Build

```bash
./build.sh
```

Github is set up to build on push

# Deploy to Runpod

Create a serverless endpoint (min 24 Gb vram, make sure to connect the shared drive with the flux model and loras)
Add env variables:

```
COMFY_POLLING_MAX_RETRIES # number of retries while waiting for a job, 1 retry per second
LOKI_URL # set this to send logs to remote loki instance (e.g. Grafana Cloud)
# put following values into runpod serets first
BUCKET_ENDPOINT_URL = {{ RUNPOD_SECRET_flux-app_s3_bucket_url }}
BUCKET_ACCESS_KEY_ID = {{ RUNPOD_SECRET_flux-app_s3_access_key_id }}
BUCKET_SECRET_ACCESS_KEY = {{ RUNPOD_SECRET_flux-app_s3_secret }}
```