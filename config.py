from dotenv import load_dotenv
import os
from pathlib import Path

env_path = str(Path(__file__).parent / ".env")


class Settings:
    def __init__(self, env_file=env_path):
        load_dotenv(env_file)
        
        self.PYRAMID_USERNAME = os.getenv("PYRAMID_USERNAME")
        self.PYRAMID_PSW = os.getenv("PYRAMID_PSW")
        self.CRED_FILE = str(Path(__file__).parent / "pyramid_creds.pkl")
        self.PYRAMID_ROOT_API_URL = "https://s00-pml-web1.hq.vlmrk.corp:8080/api/v1"
        self.GITHUB_API = "https://api.github.com/repos/sega-gremlen/simple_pyramid/releases/latest"
        self.FALLBACK_EXE_URL = "https://releases.sega-gremlen.top/simple_pyramid.exe"
        
        
settings = Settings()
