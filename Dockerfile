# Use uma imagem base Python
FROM python:3.9-slim

# Define o diretório de trabalho dentro do contêiner
WORKDIR /app

# Limpa o cache do apt e atualiza a lista de pacotes
RUN apt-get clean && apt-get update

# Instala as dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Tenta instalar as dependências do sistema operacional para o playwright
RUN playwright install-deps

# Instala os navegadores do playwright
RUN playwright install

# Copia o restante do código da aplicação Flask
COPY . .

# Expõe a porta que a aplicação Flask vai usar
EXPOSE 5000

# Comando para iniciar a aplicação Flask
# Substitua 'app:app' se o nome da instância Flask for diferente
CMD ["flask", "run", "--debug", "--host=0.0.0.0", "--port=5000"]
