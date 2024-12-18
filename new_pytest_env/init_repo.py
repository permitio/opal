import requests

with open("rbac.rego") as f:
    contents = f.read()

url = "http://localhost:3000/api/v1/repos/ariAdmin2/opal-example-policy-repo/contents/rbac.rego"
response = requests.put(url, 
                        headers={"Authorization": "token 7585f7b0b3990fd13999d71723a3e9d0504e6c2c"},
                        json={"content": contents, "branch": "master", "message": "init repo"})
assert response.status_code == 201, response.text
