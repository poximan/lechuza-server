# Crear y activar entorno virtual
python -m  venv email_service\venv
.\email_service\venv\Scripts\activate.ps1

# Instalar dependencias
pip install -r .\email_service\requirements.txt

# Levantar el servicio en 127.0.0.1:8081
python -m email_service.main
