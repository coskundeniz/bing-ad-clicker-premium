FROM python:3.11.12-slim-bookworm

# install required packages
RUN apt-get update && apt-get install -y \
    wget gnupg \
    python3-tk python3-dev xvfb \
    libnss3 libxss1 libatk-bridge2.0-0 libgtk-3-0 \
    libdrm2 libxcomposite1 libxrandr2 libgbm1 libasound2 \
    fonts-liberation \
  && rm -rf /var/lib/apt/lists/*

# install google chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | apt-key add -
RUN sh -c 'echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google-chrome.list'
RUN apt-get -y update
RUN apt-get install -y google-chrome-stable && rm -rf /var/lib/apt/lists/*

# set the working directory to /src
WORKDIR /src

# upgrade pip
RUN python -m pip install --no-cache-dir --upgrade pip

# install dependencies
COPY ./requirements.txt /src
RUN python -m pip install --no-cache-dir -r requirements.txt

# copy the current directory contents into the image
COPY . /src

# set display port to avoid crash
ENV DISPLAY=:99

# start Xvfb
CMD Xvfb :99 -screen 0 1920x1080x16 -ac +extension GLX +render -noreset

RUN python3 - <<EOF
from undetected_chromedriver.patcher import Patcher
p = Patcher()
p.auto()
EOF

ENTRYPOINT ["python"]
