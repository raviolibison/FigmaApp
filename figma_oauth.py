from flask import Flask, request, redirect, session
from dotenv import load_dotenv
import requests
import os

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24).hex()

FIGMA_CLIENT_ID = os.environ["FIGMA_CLIENT_ID"]
FIGMA_CLIENT_SECRET = os.environ["FIGMA_CLIENT_SECRET"]

REDIRECT_URI = "http://localhost:5000/callback"


@app.route("/")
def index():
    return '''
    <h1>Figma OAuth Test</h1>
    <a href="/login">Login with Figma</a>
    '''


@app.route("/login")
def login():
    figma_auth_url = (
        f"https://www.figma.com/oauth"
        f"?client_id={FIGMA_CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope=file_content:read file_metadata:read file_comments:read current_user:read"
        f"&state=random_state_string"
        f"&response_type=code"
    )
    return redirect(figma_auth_url)


@app.route("/callback")
def callback():
    code = request.args.get("code")

    if not code:
        return "Error: No authorization code provided."

    token_url = "https://api.figma.com/v1/oauth/token"
    data = {
        "client_id": FIGMA_CLIENT_ID,
        "client_secret": FIGMA_CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "code": code,
        "grant_type": "authorization_code",
    }

    response = requests.post(token_url, data=data)

    if response.status_code == 200:
        token_data = response.json()
        access_token = token_data.get("access_token")
        session["figma_token"] = access_token
        return f"Access Token: {access_token[:20]}..."
    else:
        return f"Error fetching access token: {response.text}"


@app.route("/file/<file_key>")
def get_file(file_key):
    token = session.get("figma_token")

    if not token:
        return "Not authenticated. <a href='/login'>Login first</a>"

    headers = {"Authorization": f"Bearer {token}"}
    url = f"https://api.figma.com/v1/files/{file_key}"
    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        return f"Error: {response.text}"


@app.route("/test")
def test_api():
    token = session.get("figma_token")

    if not token:
        return "Not authenticated. <a href='/login'>Login first</a>"

    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get("https://api.figma.com/v1/me", headers=headers)

    if response.status_code == 200:
        user_data = response.json()
        return f'''
            <h1>Authentication Successful!</h1>
            <p>User ID: {user_data.get('id')}</p>
            <p>Email: {user_data.get('email')}</p>
            <p>Name: {user_data.get('handle')}</p>
            <hr>
            <pre>{response.text}</pre>
            <br>
            <a href="/">Home</a>
        '''
    else:
        return f"Error calling API: {response.text}"


if __name__ == "__main__":
    app.run(debug=True, port=5000)
