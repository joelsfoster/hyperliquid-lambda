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
  - If "long" webhook with no long position: Open new long
  - If "long" webhook with existing long: Add to position
  - If "long" webhook with existing short: Reduce short
  - Same logic applies for short positions (vice versa)
  - "close" action closes all positions
- Configurable trade size based on percent of available balance
- Uses maximum allowable leverage per asset
- Only supports trading perpetual futures (e.g., "CRV-USD") with cross-margin
- Only supports market orders (no limit, stop, etc.)
- Logging for easy debugging and monitoring

## Prerequisites

- AWS Account
- TradingView Pro, Pro+ or Premium subscription (for webhook support)
- Hyperliquid account with funds
- Docker installed on your development machine

## Deployment Overview

This Lambda function is deployed using a Docker container image to ensure all dependencies, including native extensions like `ckzg`, are properly compiled for the Lambda environment.

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

## Deployment Instructions

### 1. Build and Upload Docker Image

1. Clone this repository and navigate to the project directory:

```bash
git clone <your-repo-url>
cd hyperliquid-lambda
```

2. Update AWS account details in `build-lambda-container.sh`:
   - Set `AWS_ACCOUNT_ID` to your AWS account ID
   - Set `AWS_REGION` to your preferred region (e.g., "us-east-1")

3. Build and push the Docker image to Amazon ECR:

```bash
# First, make the script executable
chmod +x build-lambda-container.sh

# Then run it to build and push the image
./build-lambda-container.sh
```

If you don't have AWS CLI installed, you'll need to:
- Install AWS CLI according to the [official instructions](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- Configure AWS CLI with `aws configure`

Alternatively, you can manually deploy through the AWS Console as outlined in the instructions that will appear when running the script without AWS CLI.

### 2. Create or Update Lambda Function

1. Go to the AWS Lambda console
2. Create a new function or select your existing function
3. Choose "Container image" as the source
4. Select or enter the ECR image URI
5. Configure these function settings:
   - Memory: At least 512MB (recommended)
   - Timeout: At least 30 seconds
   - Environment variables (add all required variables listed above)

### 3. Set Up API Gateway

1. Go to the API Gateway console
2. Create a new REST API or select your existing API
3. Create a new resource and POST method
4. Set the integration type to Lambda Function
5. Select your Lambda function
6. Enable CORS if needed
7. Deploy the API to a stage
8. Note the API endpoint URL for configuring TradingView alerts

## Local Development and Testing

1. Create a `.env` file in the project root with the required variables:

```
HYPERLIQUID_PRIVATE_KEY=your_private_key
WEBHOOK_PASSWORD=your_webhook_password
HYPERLIQUID_USE_MAINNET=false  # Use testnet for testing
```

2. Run the local server with Docker for development testing:

```bash
# Build a local development image
docker build -t hyperliquid-lambda:dev .

# Run the container with local server
docker run -p 8080:8080 -v $(pwd)/.env:/var/task/.env hyperliquid-lambda:dev python local_server.py
```

3. Use ngrok to expose your local server for webhook testing:

```bash
ngrok http 8080
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
