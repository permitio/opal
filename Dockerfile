FROM python:3.8-alpine
WORKDIR /app/
# install websockets lib from github (when we publish to pypi we can remove this line)
RUN pip install --user git+https://61c18c826840c46f67f7fdada5f0928104dbe91a@github.com/acallasec/websockets.git
# Layer dependency install (for caching)
COPY requirements.txt requirements.txt
RUN pip install --user -r requirements.txt
# copy app code
COPY . ./
# install sidecar package
RUN python setup.py develop
# expose sidecar port
EXPOSE 8000
# run gunicorn
CMD gunicorn -k uvicorn.workers.UvicornWorker --workers=1 horizon.main