from flask import Flask, request, jsonify, render_template
from plaid.api import plaid_api
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid import Configuration, ApiClient
import os

# Print the current working directory for debugging
print("Current working directory:", os.getcwd())

# Your Plaid API credentials (Replace with **NEW** credentials after revoking old ones)
PLAID_CLIENT_ID = "6f80dd6a256345750015f719b20c53"
PLAID_SECRET = "d96d5223c442c4d4b9ea76834bb209"
PLAID_ENV = "sandbox"  # Change to "development" or "production" as needed

# Flask app setup
app = Flask(__name__, template_folder='templates')  # Explicitly specify the templates folder

# Plaid API Configuration
configuration = Configuration(
    host="https://sandbox.plaid.com",  # Change for different environments
    api_key={
        "clientId": PLAID_CLIENT_ID,
        "secret": PLAID_SECRET
    }
)

# Create API client
api_client = ApiClient(configuration)
client = plaid_api.PlaidApi(api_client)

@app.route('/')
def index():
    print("Rendering index.html")  # Debugging line
    return render_template('index.html')  # Ensure that the templates folder is in the same directory

@app.route('/exchange_public_token', methods=['POST'])
def exchange_public_token():
    try:
        # The public token you get from the frontend (Plaid Link)
        public_token = request.json.get('public_token')

        # Exchange the public token for an access token
        exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
        response = client.item_public_token_exchange(exchange_request)

        access_token = response['access_token']
        item_id = response['item_id']

        return jsonify({
            "access_token": access_token,
            "item_id": item_id
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# Add a test route to check if Flask is working
@app.route('/test')
def test():
    return "This is a test!"

if __name__ == "__main__":
    app.run(debug=True)
