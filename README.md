# Hyperliquid Lambda

An AWS Lambda function for processing TradingView webhooks and executing trades on the Hyperliquid exchange. This serverless trading bot automatically executes trades based on TradingView alerts, enabling automated trading strategies without maintaining a dedicated server.

## Features

- **Webhook Processing**:
  - Receive and validate webhooks from TradingView
  - Source IP validation for TradingView webhook IPs
  - Webhook password authentication for security

- **Trading Operations**:
  - Open long positions
  - Open short positions
  - Close positions (specific asset or all positions)

- **Smart Position Management**:
  - If "long" webhook with no long position: Open new long
  - If "long" webhook with existing long: Add to position
  - If "long" webhook with existing short: Reduce short
  - Same logic applies for short positions (vice versa)
  - "close" action closes all positions

- **Advanced Trading Features**:
  - Configurable trade size based on percent of available balance
  - Uses maximum allowable leverage per asset (e.g., 10x for CRV-USD)
  - Only supports trading perpetual futures with cross-margin
  - Only supports market orders (no limit, stop, etc.)
  - Comprehensive logging for debugging and monitoring

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

#### Important: API Gateway Configuration for TradingView

When setting up API Gateway for TradingView webhooks, ensure that you configure the **root path** (`/`) to receive POST requests, not a subpath. TradingView sends webhooks to the root endpoint.

#### Option 1: Set up through AWS Console (Recommended for beginners)

1. Go to the API Gateway console
2. Create a new REST API (not HTTP API)
3. Create a POST method on the **root resource** (`/`)
4. Set the integration type to Lambda Function (Use Lambda Proxy integration)
5. Select your `hyperliquid-tradingview-webhook` function
6. Deploy the API to a stage (e.g., "prod")
7. Note the API endpoint URL for configuring TradingView alerts

#### Option 2: Set up through AWS CLI (For advanced users)

```bash
# Create a REST API
aws apigateway create-rest-api --name hyperliquid-webhook-api --region your-region

# Get the API ID and root resource ID
api_id=$(aws apigateway get-rest-apis --query "items[?name=='hyperliquid-webhook-api'].id" --output text --region your-region)
root_resource_id=$(aws apigateway get-resources --rest-api-id $api_id --query "items[?path=='/'].id" --output text --region your-region)

# Create a POST method on the root resource
aws apigateway put-method --rest-api-id $api_id --resource-id $root_resource_id --http-method POST --authorization-type NONE --region your-region

# Create the Lambda integration
aws apigateway put-integration --rest-api-id $api_id --resource-id $root_resource_id --http-method POST --type AWS_PROXY --integration-http-method POST --uri arn:aws:apigateway:your-region:lambda:path/2015-03-31/functions/arn:aws:lambda:your-region:your-account-id:function:hyperliquid-tradingview-webhook/invocations --region your-region

# Deploy the API to a stage
aws apigateway create-deployment --rest-api-id $api_id --stage-name prod --region your-region
```

### 5. Add Lambda Permission for API Gateway

Grant permission for API Gateway to invoke your Lambda function:

```bash
aws lambda add-permission \
--function-name hyperliquid-tradingview-webhook \
--statement-id apigateway-permission \
--action lambda:InvokeFunction \
--principal apigateway.amazonaws.com \
--source-arn "arn:aws:execute-api:your-region:your-account-id:$api_id/*/POST/" \
--region your-region
```

### 6. Test Your API Gateway Endpoint

Before setting up TradingView, test your API endpoint with a curl command:

```bash
curl -X POST \
  https://your-api-id.execute-api.your-region.amazonaws.com/prod \
  -H "Content-Type: application/json" \
  -d '{"action": "long", "ticker": "BTC", "amountPercent": 1, "password": "your_webhook_password"}'
```

Note: Replace `your_webhook_password` with the actual password you've set in your Lambda environment variables.

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

### Prerequisites
- TradingView Pro, Pro+, or Premium subscription (required for webhook functionality)
- An active API Gateway endpoint as configured in previous steps

### Creating Alerts for Different Actions

#### 1. Long Position Alert

1. In TradingView, open a chart for the asset you want to trade (e.g., BTC, ETH, CRV)
2. Click the "Alerts" icon in the right sidebar
3. Click "Create Alert"
4. Configure your alert conditions (price crossing, indicator signals, etc.)
5. In the "Alert actions" section, select "Webhook URL"
6. Enter your API Gateway URL: `https://your-api-id.execute-api.your-region.amazonaws.com/prod`
7. In the alert message body, enter:

```json
{
  "action": "long",
  "ticker": "{{ticker}}",
  "amountPercent": 10,
  "password": "your_webhook_password"
}
```

#### 2. Short Position Alert

Follow the same steps as above, but use this message body:

```json
{
  "action": "short",
  "ticker": "{{ticker}}",
  "amountPercent": 10,
  "password": "your_webhook_password"
}
```

#### 3. Close Position Alert

Follow the same steps as above, but use this message body:

```json
{
  "action": "close",
  "ticker": "{{ticker}}",
  "password": "your_webhook_password"
}
```

### Webhook Format Details

| Field | Description | Required | Default |
|-------|-------------|----------|--------|
| `action` | Trading action: `"long"`, `"short"`, or `"close"` | Yes | N/A |
| `ticker` | Asset symbol (e.g., `"BTC"`, `"ETH"`, `"CRV"`) | Yes | N/A |
| `amountPercent` | Percentage of available balance to use (1-100) | No | 5 |
| `password` | Webhook authentication password | Yes | N/A |

### Position Management Logic

This bot implements smart position management:

- **Long webhook**:
  - No existing long: Opens a new long position
  - Existing long: Adds to the position
  - Existing short: Reduces the short position

- **Short webhook**:
  - No existing short: Opens a new short position
  - Existing short: Adds to the position
  - Existing long: Reduces the long position

- **Close webhook**:
  - Closes all positions for the specified asset

### Trading Settings

- Uses **maximum allowable leverage** for each asset (varies by asset)
- Only supports **market orders** (no limit, stop, etc.)
- Only works with **perpetual futures** on Hyperliquid
- Uses **cross-margin** for all trades

## Security

### Webhook Authentication

This Lambda function implements several security measures:

1. **Password Authentication**: Each webhook must include the correct password in the payload
2. **IP Validation**: By default, only requests from known TradingView IP addresses are accepted
3. **HTTPS Encryption**: All API Gateway endpoints use HTTPS (port 443) for secure communication

### Securing Your Private Key

The Lambda function requires your Hyperliquid private key to execute trades. To keep it secure:

1. **Never commit your private key** to version control
2. Store it as an encrypted environment variable in AWS Lambda
3. Use AWS Parameter Store or Secrets Manager for additional security
4. Consider rotating your private key periodically

## Troubleshooting

### Common Issues

#### Lambda Function Not Receiving Webhooks

1. **API Gateway Configuration**: Ensure your API Gateway is set up with a POST method on the **root path** (`/`), not a subpath
2. **Lambda Permissions**: Verify API Gateway has permission to invoke your Lambda function
3. **Webhook URL**: Double-check the webhook URL in your TradingView alerts matches your API Gateway endpoint exactly

#### Lambda Function Receiving Webhooks But Not Trading

1. **Invalid Password**: Check that the webhook password matches your Lambda environment variable
2. **Missing Environment Variables**: Ensure all required environment variables are set in Lambda:
   - `HYPERLIQUID_PRIVATE_KEY`
   - `WEBHOOK_PASSWORD`
   - `HYPERLIQUID_USE_MAINNET`
3. **Insufficient Funds**: Verify your Hyperliquid account has sufficient funds for trading

### Checking Logs

To view Lambda execution logs:

```bash
aws logs get-log-events \
  --log-group-name /aws/lambda/hyperliquid-tradingview-webhook \
  --log-stream-name $(aws logs describe-log-streams \
    --log-group-name /aws/lambda/hyperliquid-tradingview-webhook \
    --order-by LastEventTime \
    --descending \
    --limit 1 \
    --query 'logStreams[0].logStreamName' \
    --output text) \
  --region your-region
```

Alternatively, view logs in the AWS Lambda console under the "Monitor" tab.

## Additional Security Best Practices

- Use IAM roles with least privilege for the Lambda function
- Consider enabling AWS CloudTrail for auditing API calls
- Regularly review CloudWatch logs for suspicious activity

## Repository Information

This project is maintained by Joel Foster.

- **GitHub Repository**: [https://github.com/joelsfoster/hyperliquid-lambda](https://github.com/joelsfoster/hyperliquid-lambda)
- **License**: MIT

## Related Projects

- [Hyperliquid CLI](https://github.com/joelsfoster/hyperliquid-cli) - A Python CLI for trading on Hyperliquid

## License

MIT License
