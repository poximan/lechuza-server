docker rm -f cont-panelexemys
docker build -t img-panelexemys .
docker run -d --restart unless-stopped --name cont-panelexemys -p 8050:8051 -v ./data:/app/data img-panelexemys