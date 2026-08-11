FROM python:3.11-slim

RUN apt-get update && apt-get install -y wget gnupg curl unzip ca-certificates \
    && wget -q -O /usr/share/keyrings/google-chrome-key.pub https://dl-ssl.google.com/linux/linux_signing_key.pub \
    && gpg --dearmor -o /usr/share/keyrings/google-chrome-keyring.gpg /usr/share/keyrings/google-chrome-key.pub \
    && echo "deb [signed-by=/usr/share/keyrings/google-chrome-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY fubon_vcct_calculator.py .

CMD ["python", "fubon_vcct_calculator.py"]
