# app.py
import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask
from flask_restx import Api
from src.routes import bp as seger_bp

def configure_logging(app):
    # --- Logging Setup ---
    log_dir = 'src/logs'
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_file = os.path.join(log_dir, 'swagger_api.log')

    # Create a file handler for the API logger
    file_handler = RotatingFileHandler(log_file, maxBytes=10485760, backupCount=3)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)

    # Add the handler to the Flask app's logger
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)
    app.logger.info('Swagger API startup')
    # --- End Logging Setup ---

def create_app():
    app = Flask(__name__)

    configure_logging(app)
    
    # Configuração do Swagger/OpenAPI
    api = Api(
        app,
        version='1.0',
        title='Seger API',
        description='API para gestão de eficiência energética - Sistema de análise e otimização de faturas de energia',
        doc='/swagger/',
        prefix='/api'
    )
    
    # Registra o namespace do seger
    api.add_namespace(seger_bp, path='/seger')
    
    return app

if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=5001, debug=False)
