from opal_client.client import OpalClient

client = OpalClient()

import debugpy
#debugpy.listen(("0.0.0.0", 5678))
print("Waiting for debugger attach...")
#debugpy.wait_for_client()  # Optional, wait for debugger to attach before continuing

# expose app for Uvicorn
app = client.app
