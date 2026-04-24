# Crear y activar entorno virtual
python -m  venv email_client\venv
.\email_client\venv\Scripts\activate.ps1

# Instalar dependencias
pip install -r .\email_client\requirements.txt

# Variables de entorno
$env:SERVICE_BASE_URL="http://127.0.0.1:8081"
$env:API_KEY="miclave"

# Probar cliente (sync/async)
python -m email_client.client