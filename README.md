# Hyperliquid Lambda

An AWS Lambda function for processing TradingView webhooks and executing trades on the Hyperliquid exchange.

## Features

- Receive and validate webhooks from TradingView
- Source IP validation for TradingView webhook IPs
- Webhook password authentication
- Trading operations:
  - Open long positions
  - Open short positions
  - Close all positions
- Smart position management:
  - Auto-close opposite direction positions before opening new positions
  - Add to existing positions in the same direction
  - Reduce opposite positions with partial trades
- Configurable trade size based on percent of available balance
- Uses maximum allowable leverage per asset
- Logging for easy debugging and monitoring

## Prerequisites

- AWS Account
- TradingView Pro, Pro+ or Premium subscription (for webhook support)
- Hyperliquid account with funds
- Python 3.9+

## Environment Variables

Configure the following environment variables in your AWS Lambda:

- `HYPERLIQUID_PRIVATE_KEY`: Your Hyperliquid wallet private key
- `WEBHOOK_PASSWORD`: A secure password for webhook validation
- `HYPERLIQUID_USE_MAINNET`: Set to "true" for mainnet or "false" for testnet (default: "true")

## Webhook Format

TradingView should send a POST request with the following JSON payload:

```json
{
  "action": "long|short|close",
  "ticker": "BTC",
  "amountPercent": 5,
  "password": "your_webhook_password"
}
```

- `action`: The action to take (long, short, or close)
- `ticker`: The asset to trade (e.g., BTC, ETH, CRV)
- `amountPercent`: Percentage of available balance to use (1-100, default: 5)
- `password`: The webhook password configured in the Lambda environment

## Local Development and Testing

1. Create a `.env` file in the project root with the required variables:

```
HYPERLIQUID_PRIVATE_KEY=your_private_key
WEBHOOK_PASSWORD=your_webhook_password
HYPERLIQUID_USE_MAINNET=false  # Use testnet for testing
```

2. Install dependencies:

```
pip install -r requirements.txt
```

3. Run the local test server and use ngrok for webhook testing:

```bash
# Start ngrok to expose your local server
ngrok http 80

# In another terminal, start the local server
python local_server.py
```

4. The server will display your ngrok URL for configuring with TradingView:

```python
from http.server import BaseHTTPRequestHandler, HTTPServer
import sys
import json
from src.lambda_function import lambda_handler

# Local server implementation has been provided in local_server.py
# Just run the server with:
# python local_server.py
```

5. Configure your TradingView alert to use the ngrok URL displayed by the local server

## Deployment to AWS Lambda

1. Package your application:

```bash
# Create a deployment package
mkdir -p package
pip install -r requirements.txt -t package/
cp -r src package/
cd package
zip -r ../deployment-package.zip .
cd ..
```

2. Create a Lambda function in the AWS Management Console:
   - Runtime: Python 3.9+
   - Handler: src.lambda_function.lambda_handler
   - Timeout: 60 seconds (trades can take some time to execute)
   - Memory: 256MB should be sufficient

3. Upload the deployment package to Lambda:
   - In the Lambda console, select your function
   - Under "Code source", select "Upload from" → ".zip file"
   - Upload your deployment-package.zip file

4. Configure environment variables in the Lambda console:
   - HYPERLIQUID_PRIVATE_KEY
   - WEBHOOK_PASSWORD
   - HYPERLIQUID_USE_MAINNET

5. Set up API Gateway:
   - Create a new REST API
   - Add a POST method to the root resource
   - Deploy the API to a stage
   - Use the provided URL for your TradingView webhook
   
6. Configure Lambda resource policies to allow API Gateway to invoke the function

## Setting Up TradingView Alerts

1. Create a new alert in TradingView
2. Set the "Alert actions" to "Webhook URL"
3. Enter your API Gateway URL
4. Configure the alert message body:

```json
{
  "action": "long",
  "ticker": "{{ticker}}",
  "amountPercent": 5,
  "password": "your_webhook_password"
}
```

5. Adjust `action` to "short" or "close" as needed
6. Adjust `amountPercent` to control position size

## Security

- Protect your private key and webhook password
- Use API Gateway's resource policies to restrict access to TradingView IPs
- Consider enabling AWS CloudTrail for auditing
- Use IAM roles with least privilege for the Lambda function

## Position Management Logic

This Lambda implements smart position management with the following behavior:

- If "long" webhook with no existing position: Opens a new long position
- If "long" webhook with existing long position: Adds to the existing position
- If "long" webhook with existing short position: Closes the existing short, then opens a new long position
- Same logic applies for "short" positions (vice versa)
- "close" action closes all positions for the specified asset

## Known Limitations

- Only supports market orders (no limit, stop, or other order types)
- Uses maximum available leverage for each asset
- Only validates known TradingView IP addresses
- Only supports cross-margin trading
