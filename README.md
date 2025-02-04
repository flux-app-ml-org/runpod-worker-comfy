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