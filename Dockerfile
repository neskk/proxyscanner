# For more information, please refer to https://aka.ms/vscode-docker-python
#FROM python:3-alpine
FROM python:3.7-alpine

# Keeps Python from generating .pyc files in the container
ENV PYTHONDONTWRITEBYTECODE=1

# Turns off buffering for easier container logging
ENV PYTHONUNBUFFERED=1

WORKDIR /usr/src/app

# Install pip requirements
COPY app/requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt

# Copy app folder to the container
COPY ./app /usr/src/app

# Creates a non-root user with an explicit UID and adds permission to access the /app folder
# For more info, please refer to https://aka.ms/vscode-docker-python-configure-containers
RUN adduser -u 5678 --disabled-password --gecos "" appuser && chown -R appuser /usr/src/app
USER appuser

# This entry point will be overridden by docker-compose. For more information, please refer to https://aka.ms/vscode-docker-python-debug
CMD ["python", "start.py"]
