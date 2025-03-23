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

2. Build the Docker image with the required flags to ensure AWS Lambda compatibility:

```bash
# Build the Docker image with provenance=false to ensure AWS Lambda compatibility
docker build --platform=linux/amd64 --provenance=false -t hyperliquid-lambda:latest .
```

> **Important**: The `--provenance=false` flag is critical when building Docker images for AWS Lambda. Without this flag, the image manifest format may be incompatible with Lambda, resulting in the error: "The image manifest, config or layer media type for the source image is not supported."

3. Create an Amazon ECR repository (if you don't already have one):

```bash
aws ecr create-repository --repository-name hyperliquid-lambda --region your-region
```

4. Authenticate Docker to your ECR registry:

```bash
aws ecr get-login-password --region your-region | docker login --username AWS --password-stdin your-account-id.dkr.ecr.your-region.amazonaws.com
```

5. Tag and push the Docker image to Amazon ECR:

```bash
# Tag the image
docker tag hyperliquid-lambda:latest your-account-id.dkr.ecr.your-region.amazonaws.com/hyperliquid-lambda:latest

# Push the image
docker push your-account-id.dkr.ecr.your-region.amazonaws.com/hyperliquid-lambda:latest
```

Replace `your-account-id` and `your-region` with your AWS account ID and preferred region.

### 2. Create the Lambda Function

1. Create the Lambda function using the AWS CLI (replace placeholders with your actual values):

```bash
aws lambda create-function \
--region your-region \
--function-name hyperliquid-tradingview-webhook \
--package-type Image \
--code ImageUri=your-account-id.dkr.ecr.your-region.amazonaws.com/hyperliquid-lambda:latest \
--role arn:aws:iam::your-account-id:role/your-lambda-execution-role \
--timeout 60 \
--memory-size 256
```

Alternatively, through the AWS Lambda console:

1. Go to the AWS Lambda console
2. Create a new function
3. Choose "Container image" as the source
4. Select the ECR image URI you pushed earlier
5. Configure these function settings:
   - Memory: 256MB (or more if needed)
   - Timeout: 60 seconds

### 3. Configure Environment Variables

Add the required environment variables via the AWS console:

1. Go to your Lambda function
2. Select the "Configuration" tab
3. Click on "Environment variables"
4. Add the following environment variables:
   - `HYPERLIQUID_PRIVATE_KEY`: Your Hyperliquid wallet private key
   - `WEBHOOK_PASSWORD`: A secure password for webhook validation
   - `HYPERLIQUID_USE_MAINNET`: Set to "true" for mainnet or "false" for testnet

### 4. Set Up API Gateway

1. Create an API Gateway using the AWS CLI:

```bash
# Create a REST API
aws apigateway create-rest-api --name hyperliquid-webhook-api --region your-region

# Get the API ID and root resource ID (save these values for subsequent commands)
api_id=$(aws apigateway get-rest-apis --query "items[?name=='hyperliquid-webhook-api'].id" --output text --region your-region)
root_resource_id=$(aws apigateway get-resources --rest-api-id $api_id --query "items[?path=='/'].id" --output text --region your-region)

# Create a POST method on the root resource
aws apigateway put-method --rest-api-id $api_id --resource-id $root_resource_id --http-method POST --authorization-type NONE --region your-region

# Create the Lambda integration
aws apigateway put-integration --rest-api-id $api_id --resource-id $root_resource_id --http-method POST --type AWS_PROXY --integration-http-method POST --uri arn:aws:apigateway:your-region:lambda:path/2015-03-31/functions/arn:aws:lambda:your-region:your-account-id:function:hyperliquid-tradingview-webhook/invocations --region your-region
```

Or alternatively through the AWS Console:

1. Go to the API Gateway console
2. Create a new REST API
3. Create a POST method on the root resource
4. Set the integration type to Lambda Function
5. Select your `hyperliquid-tradingview-webhook` function
6. Enable CORS if needed
7. Deploy the API to a stage (e.g., "prod")
8. Note the API endpoint URL for configuring TradingView alerts

### 5. Add Lambda Permission for API Gateway

```bash
aws lambda add-permission \
--function-name hyperliquid-tradingview-webhook \
--statement-id apigateway-permission \
--action lambda:InvokeFunction \
--principal apigateway.amazonaws.com \
--source-arn "arn:aws:execute-api:your-region:your-account-id:$api_id/*/POST/" \
--region your-region
```

## Local Development and Testing

1. Create a `.env` file in the project root with the required variables:

```
HYPERLIQUID_PRIVATE_KEY=your_private_key
WEBHOOK_PASSWORD=your_webhook_password
HYPERLIQUID_USE_MAINNET=false  # Use testnet for testing
```

2. Run the local server with Docker for development testing:

```bash
# Build a local development image with the proper flags
docker build --platform=linux/amd64 --provenance=false -t hyperliquid-lambda:dev .

# Run the container with local server
docker run -p 8080:8080 -v $(pwd)/.env:/var/task/.env hyperliquid-lambda:dev python local_server.py
```

3. Use ngrok to expose your local server for webhook testing:

```bash
ngrok http 8080
```

4. Configure your TradingView alert to use the ngrok URL displayed by the local server

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
