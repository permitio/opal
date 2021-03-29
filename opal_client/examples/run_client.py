from opal_client.main import app
import uvicorn

uvicorn.run(app, port=9000)