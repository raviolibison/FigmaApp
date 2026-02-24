from flask import Flask, request, redirect, session
from dotenv import load_dotenv
from openai import OpenAI
import requests
import os
import csv
import io
import json

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ["FLASK_SECRET_KEY"]

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
        

def analyze_figma_with_chatgpt(figma_data, categories):
    """Send Figma JSON to ChatGPT for analysis, get structured JSON back"""
    
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    # Build category list for prompt
    categories_list = "\n".join([f"- {cat}" for cat in categories])
    
    system_prompt = """You are a precise Figma design analysis tool.

CRITICAL RULES:
1. Extract ONLY information explicitly present in the JSON
2. NEVER infer, assume, or hallucinate information
3. If a category has no relevant data, mark finding as "Not Found"
4. Cite specific locations in the JSON structure
5. Be conservative - when in doubt, say "Not Found"
"""
    
    user_prompt = f"""
Analyze this Figma design file JSON and extract information for these categories:

{categories_list}

For each category, return:
- category: exact category name from the list
- finding: the extracted information, or "Not Found" if not present
- confidence: "High" / "Medium" / "Low" / "None" (use "None" for "Not Found")
- source: where in the JSON you found it (e.g., "Page 2, Frame: Login") or "N/A"

Return as a JSON array with this EXACT structure:
[
  {{
    "category": "Category Name",
    "finding": "description or 'Not Found'",
    "confidence": "High/Medium/Low/None",
    "source": "location or 'N/A'"
  }}
]

Return ONLY the JSON array, no explanation.

Figma JSON:
{json.dumps(figma_data, indent=2)[:15000]}
"""  # Truncate to avoid token limits
    
    response = client.chat.completions.create(
        model="gpt-5-nano",
        temperature=0,  # Most deterministic
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
    )
    
    # Parse JSON response
    try:
        result = json.loads(response.choices[0].message.content)
        return result
    except json.JSONDecodeError:
        # Fallback: try to extract JSON from response
        content = response.choices[0].message.content
        # Sometimes ChatGPT wraps it in ```json blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        return json.loads(content)


def convert_to_csv(json_data):
    """Convert JSON analysis to CSV format"""
    output = io.StringIO()
    writer = csv.DictWriter(
        output, 
        fieldnames=['Category', 'Finding', 'Confidence', 'Source']
    )
    writer.writeheader()
    
    for item in json_data:
        writer.writerow({
            'Category': item['category'],
            'Finding': item['finding'],
            'Confidence': item['confidence'],
            'Source': item['source']
        })
    
    return output.getvalue()


# Add this endpoint
@app.route("/api/figma/analyze/<file_key>")
def analyze_figma_file(file_key):
    """Analyze Figma file with ChatGPT and return CSV"""
    token = session.get("figma_token")
    
    if not token:
        return {"error": "Not authenticated", "auth_url": "/login"}, 401
    
    # Fetch Figma file
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(
        f"https://api.figma.com/v1/files/{file_key}",
        headers=headers
    )
    
    if response.status_code != 200:
        return {"error": response.text}, response.status_code
    
    figma_data = response.json()
    
    # Define your categories (customize these!)
    categories = [
        "User Journey",
        "Design Pattern",
        "Color Scheme",
        "Typography",
        "Accessibility Features",
        "Navigation Structure",
        "Form Validation Rules",
        "Responsive Breakpoints"
    ]
    
    # Analyze with ChatGPT
    try:
        analysis_json = analyze_figma_with_chatgpt(figma_data, categories)
        
        # Convert to CSV
        csv_content = convert_to_csv(analysis_json)
        
        # Clean up token
        revoke_figma_token(token)
        session.pop("figma_token", None)
        
        # Return CSV file
        return csv_content, 200, {
            'Content-Type': 'text/csv',
            'Content-Disposition': f'attachment; filename=figma_{file_key}_analysis.csv'
        }
        
    except Exception as e:
        return {"error": str(e)}, 500


def revoke_figma_token(token):
    """Revoke Figma access token"""
    try:
        revoke_url = "https://api.figma.com/v1/oauth/revoke"
        data = {
            'client_id': FIGMA_CLIENT_ID,
            'client_secret': FIGMA_CLIENT_SECRET,
            'token': token
        }
        requests.post(revoke_url, data=data)
    except Exception as e:
        print(f"Error revoking token: {e}")


if __name__ == "__main__":
    app.run(debug=True, port=5000)
