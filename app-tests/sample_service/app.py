from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# OPAL Authorization endpoint
OPAL_AUTH_URL = "http://opal_client:8181/v1/data/authorize"  # Adjust with actual OPAL endpoint

@app.route('/a')
def a():
    return 'Endpoint A'

@app.route('/b')
def b():
    return 'Endpoint B'

@app.route('/c')
def c():
    # Assuming the JWT token is passed in the Authorization header
    auth_header = request.headers.get('Authorization')

    if not auth_header:
        return jsonify({"error": "Unauthorized, missing Authorization header"}), 401

    # Extract the token (assuming Bearer token)
    token = auth_header.split(" ")[1] if "Bearer" in auth_header else None

    if not token:
        return jsonify({"error": "Unauthorized, invalid Authorization header"}), 401

    import jwt

    try:
        # Decode the JWT token to extract the "sub" field
        decoded_token = jwt.decode(token, options={"verify_signature": False})
        user = decoded_token.get("sub")
    except jwt.DecodeError:
        return jsonify({"error": "Unauthorized, invalid token"}), 401

    if not user:
        return jsonify({"error": "Unauthorized, 'sub' field not found in token"}), 401

    # Prepare the payload for the OPAL authorization request with the extracted user
    payload = {
        "input": {
            "user": user,
            "method": request.method,
            "path": request.path
        }
    }

    # Send the request to OPAL authorization endpoint
    try:
        response = requests.post(OPAL_AUTH_URL, json=payload)

        # If the authorization is denied, return 403 Forbidden
        if response.status_code != 200:
            return jsonify({"error": "Forbidden, authorization failed"}), 403

        # Proceed to endpoint logic if authorized
        return 'Endpoint C - Authorized'

    except requests.exceptions.RequestException as e:
        # Handle errors in calling OPAL (e.g., connection issues)
        return jsonify({"error": f"Error contacting OPAL client: {str(e)}"}), 500


if __name__ == '__main__':
    app.run()