import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR      = os.path.join(os.getcwd(), "faturas_edp")
EDP_LOGIN     = os.getenv("EDP_LOGIN_EMAIL", "")
EDP_PASSWORD  = os.getenv("EDP_LOGIN_SENHA", "")
