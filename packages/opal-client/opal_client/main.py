from .client import OpalClient

client = OpalClient()
# expose app for Uvicorn
app = client.app
