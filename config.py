from dotenv import load_dotenv
import os


class Settings:
    def __init__(self, env_file=".env"):
        load_dotenv(env_file)
        
        # self.PYRAMID_USERNAME = os.getenv("PYRAMID_USERNAME")
        # self.PYRAMID_PSW = os.getenv("PYRAMID_PSW")
        # self.PYRAMID_ROOT_API_URL = os.getenv("PYRAMID_ROOT_API_URL")
        self.PYRAMID_ROOT_API_URL = "https://s00-pml-web1.hq.vlmrk.corp:8080/api/v1"
        self.GITHUB_API = "https://api.github.com/repos/sega-gremlen/simple_pyramid/releases/latest"
        
    # def __str__(self):
    #     return f"{self.PYRAMID_USERNAME=}\n" \
    # f"{self.PYRAMID_PSW=}\n" \
    # f"{self.PYRAMID_ROOT_API_URL=}" \
        
        
settings = Settings()
