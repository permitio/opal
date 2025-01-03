from flask import Flask, request, jsonify
import requests
import debugpy

app = Flask(__name__)

debugpy.listen(("0.0.0.0", 5682))  # Optional, listen for debug requests on port 5678

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

    debugpy.wait_for_client()
    
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

        # Check if OPAL's response contains a positive authorization result
        if response.status_code == 200:
            opal_response = response.json()
            if opal_response.get("result") is True:
                return 'Endpoint C - Authorized'  # Authorized access

            # If the result is not `true`, deny access
            
            # Assuming `response` is your variable containing the response object from OPAL
            response_data = response.get_data(as_text=True) 
            return jsonify({"error": f"Forbidden, authorization denied! \n Response Body: {response_data}"}), 403
        # OPAL responded but with a non-200 status, treat as denied
        return jsonify({"error": "Forbidden, OPAL authorization failed"}), 403

    except requests.exceptions.RequestException as e:
        # Handle connection or other request errors
        return jsonify({"error": f"Error contacting OPAL client: {str(e)}"}), 500

if __name__ == '__main__':
    app.run()