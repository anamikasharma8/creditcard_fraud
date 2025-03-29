from flask import Flask, request, jsonify, render_template
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_response import LinkTokenCreateResponse
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
from plaid.model.country_code import CountryCode
from plaid.model.products import Products
from plaid import Configuration, ApiClient
import os
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Your Plaid API credentials
PLAID_CLIENT_ID = '67e196f190625d0022c98475'
PLAID_SECRET = 'd96d5223c442c4d4b9ea76834bb209'
PLAID_ENV = 'sandbox'

if not PLAID_CLIENT_ID or not PLAID_SECRET:
    raise ValueError(
        "The Plaid API credentials are missing. Please ensure you have set "
        "PLAID_CLIENT_ID and PLAID_SECRET environment variables or created a .env file."
    )

# Flask app setup
app = Flask(__name__, template_folder='templates')

# Plaid API Configuration
host_map = {
    'sandbox': 'https://sandbox.plaid.com',
    'development': 'https://development.plaid.com',
    'production': 'https://production.plaid.com'
}

configuration = Configuration(
    host=host_map.get(PLAID_ENV, 'https://sandbox.plaid.com'),
    api_key={
        "clientId": PLAID_CLIENT_ID,
        "secret": PLAID_SECRET
    }
)

# Create API client
api_client = ApiClient(configuration)
client = plaid_api.PlaidApi(api_client)

def create_sandbox_public_token(institution_id="ins_1"):
    """Create a sandbox public token for testing"""
    try:
        response = requests.post(
            f"{configuration.host}/sandbox/public_token/create",
            headers={
                "Content-Type": "application/json",
                "Plaid-Client-Id": PLAID_CLIENT_ID,
                "Plaid-Secret": PLAID_SECRET
            },
            json={
                "institution_id": institution_id,
                "initial_products": ["transactions"]
            }
        )
        return response.json().get('public_token')
    except Exception as e:
        print(f"Error creating sandbox public token: {str(e)}")
        return None

@app.route('/')
def index():
    print("Rendering index.html")
    return render_template('index.html')

@app.route('/create_link_token', methods=['GET'])
def create_link_token():
    try:
        print("Creating link token...")
        request = LinkTokenCreateRequest(
            client_name="Fraud Detection App",
            country_codes=[CountryCode("US")],
            language="en",
            user={
                "client_user_id": str(datetime.now().timestamp())
            },
            products=[Products("auth"), Products("transactions")]
        )
        
        print("Sending request to Plaid...")
        response = client.link_token_create(request)
        print("Received response from Plaid")
        
        if not response or 'link_token' not in response:
            print("No link token in response")
            return jsonify({"error": "Failed to create link token"}), 400
            
        link_token = response['link_token']
        print(f"Successfully created link token: {link_token[:10]}...")

        # If in sandbox mode, create a public token for testing
        if PLAID_ENV == "sandbox":
            public_token = create_sandbox_public_token()
            if public_token:
                print("Created sandbox public token")
                return jsonify({
                    "link_token": link_token,
                    "sandbox_public_token": public_token
                })

        return jsonify({"link_token": link_token})

    except Exception as e:
        print(f"Error creating link token: {str(e)}")
        return jsonify({"error": str(e)}), 400

@app.route('/exchange_public_token', methods=['POST'])
def exchange_public_token():
    try:
        public_token = request.json.get('public_token')
        if not public_token:
            return jsonify({"error": "No public token provided"}), 400

        print(f"Exchanging public token: {public_token[:10]}...")
        exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
        response = client.item_public_token_exchange(exchange_request)

        access_token = response['access_token']
        item_id = response['item_id']
        print(f"Successfully exchanged token for access_token: {access_token[:10]}...")

        return jsonify({
            "access_token": access_token,
            "item_id": item_id
        })
    
    except Exception as e:
        print(f"Error exchanging public token: {str(e)}")
        return jsonify({"error": str(e)}), 400

@app.route('/get_transactions', methods=['POST'])
def get_transactions():
    try:
        access_token = request.json.get('access_token')
        if not access_token:
            return jsonify({"error": "No access token provided"}), 400
        
        print(f"Fetching transactions for access_token: {access_token[:10]}...")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        plaid_request = TransactionsGetRequest(
            access_token=access_token,
            start_date=start_date.date(),
            end_date=end_date.date(),
            options=TransactionsGetRequestOptions(
                count=100
            )
        )
        
        try:
            response = client.transactions_get(plaid_request)
            print("Raw Plaid response:", response)  # Debug log
            
            if not response:
                print("Empty response from Plaid")
                return jsonify({"error": "Empty response from Plaid"}), 400
                
            # Convert response to dictionary if it's not already
            if hasattr(response, 'to_dict'):
                response_dict = response.to_dict()
            else:
                response_dict = response
                
            print("Response dictionary:", response_dict)  # Debug log
            
            if 'transactions' not in response_dict:
                print("No transactions key in response")
                return jsonify({"error": "No transactions found in response"}), 400
                
            transactions = response_dict['transactions']
            print(f"Retrieved {len(transactions)} transactions")
            print("First transaction example:", transactions[0] if transactions else "No transactions")  # Debug log
            
            # Process transactions and ensure JSON serializable
            processed_transactions = process_transactions(transactions)
            
            return jsonify({
                "transactions": transactions,
                "fraud_analysis": processed_transactions
            })
        except Exception as plaid_error:
            print(f"Plaid API error: {str(plaid_error)}")
            print(f"Error type: {type(plaid_error)}")  # Debug log
            print(f"Error details: {dir(plaid_error)}")  # Debug log
            return jsonify({"error": f"Plaid API error: {str(plaid_error)}"}), 400
    
    except Exception as e:
        print(f"Error fetching transactions: {str(e)}")
        print(f"Error type: {type(e)}")  # Debug log
        print(f"Error details: {dir(e)}")  # Debug log
        return jsonify({"error": str(e)}), 400

def process_transactions(transactions):
    # Debug log
    print("Processing transactions...")
    print("First transaction before processing:", transactions[0] if transactions else "No transactions")
    
    # Convert transactions to a format suitable for fraud detection
    transaction_data = []
    for transaction in transactions:
        # Debug log for transaction structure
        print(f"Processing transaction: {transaction}")
        
        try:
            processed_transaction = {
                'amount': float(transaction.get('amount', 0.0)),
                'date': transaction.get('date', ''),
                'merchant_name': transaction.get('merchant_name', ''),
                'category': transaction.get('category', []),
                'location': transaction.get('location', {}),
                'payment_channel': transaction.get('payment_channel', ''),
                'pending': bool(transaction.get('pending', False))
            }
            transaction_data.append(processed_transaction)
        except Exception as e:
            print(f"Error processing transaction: {e}")
            print(f"Problematic transaction: {transaction}")
            continue
    
    # Convert to DataFrame for model input
    df = pd.DataFrame(transaction_data)
    print("DataFrame shape:", df.shape)  # Debug log
    
    if df.empty:
        print("No transactions to process")
        return []
    
    # Prepare features for fraud detection
    features = df[['amount']].values
    
    # Initialize and fit the model
    model = IsolationForest(contamination=0.1, random_state=42)
    predictions = model.fit_predict(features)
    
    # Convert NumPy types to Python native types
    processed_results = []
    for i, (transaction, prediction) in enumerate(zip(transactions, predictions)):
        try:
            processed_transaction = transaction.copy() if isinstance(transaction, dict) else dict(transaction)
            
            # Add fraud detection results
            processed_transaction['fraud_score'] = float(prediction)
            processed_transaction['is_fraudulent'] = bool(prediction == -1)
            
            # Ensure all values are JSON serializable
            for key, value in processed_transaction.items():
                if isinstance(value, (np.integer, np.floating)):
                    processed_transaction[key] = float(value)
                elif isinstance(value, np.bool_):
                    processed_transaction[key] = bool(value)
                elif isinstance(value, np.ndarray):
                    processed_transaction[key] = value.tolist()
                elif isinstance(value, (datetime, pd.Timestamp)):
                    processed_transaction[key] = value.isoformat()
                    
            processed_results.append(processed_transaction)
        except Exception as e:
            print(f"Error processing result for transaction {i}: {e}")
            continue
    
    print("Processed results count:", len(processed_results))  # Debug log
    return processed_results

@app.route('/analyze_transaction', methods=['POST'])
def analyze_transaction():
    try:
        transaction_data = request.json.get('transaction')
        result = process_transactions([transaction_data])
        return jsonify(result[0])
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# Add a test route to check if Flask is working
@app.route('/test')
def test():
    return "This is a test!"

if __name__ == "__main__":
    app.run(debug=True)
