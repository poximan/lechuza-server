docker rm -f cont-mensagelo
docker build -t img-mensagelo .
docker run --hostname mensagelo -d --restart unless-stopped --name cont-mensagelo -p 8081:8081 -v ./data:/app/data img-mensagelo