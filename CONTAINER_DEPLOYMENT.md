# Deploying Hyperliquid Lambda with Container Images

This guide explains how to deploy the Hyperliquid Lambda function using container images to solve dependency issues with modules like `ckzg`.

## Prerequisites

Before starting, make sure you have:

1. Docker installed and running on your machine
2. AWS CLI installed and configured with appropriate permissions
3. An AWS account with access to Lambda, ECR, and IAM services

## Setup & Deployment Steps

### 1. Update AWS Account Details

Edit the `build-lambda-container.sh` script and update the following variables:
- `AWS_ACCOUNT_ID`: Your AWS account ID
- `AWS_REGION`: The AWS region where you want to deploy (e.g., "us-east-1")

### 2. Build and Push the Container Image

Run the build script to create and push the Docker container to ECR:

```bash
./build-lambda-container.sh
```

This script will:
- Build a Docker image with all dependencies installed
- Create an ECR repository if it doesn't exist
- Push the image to ECR

### 3. Create or Update the Lambda Function

#### If Creating a New Lambda Function:

1. Go to the AWS Lambda console
2. Click "Create function"
3. Select "Container image" as the source
4. Enter a name for your function (e.g., "hyperliquid-tradingview-webhook")
5. In the "Container image URI" field, paste the ECR image URI from the script output
6. Configure the appropriate IAM role with permissions needed for your function
7. Click "Create function"

#### If Updating an Existing Lambda Function:

1. Go to the AWS Lambda console
2. Select your existing function
3. Go to the "Code" tab
4. Click "Upload from" and select "Amazon ECR"
5. Paste the ECR image URI from the script output
6. Click "Save"

### 4. Configure Lambda Function Settings

1. In the Lambda function configuration, set:
   - Memory: At least 512MB (recommended)
   - Timeout: At least 30 seconds
   
2. Configure environment variables:
   - `HYPERLIQUID_PRIVATE_KEY`: Your Hyperliquid wallet private key
   - `WEBHOOK_PASSWORD`: A secure password for webhook validation
   - `HYPERLIQUID_USE_MAINNET`: Set to "true" for mainnet or "false" for testnet

### 5. Set Up API Gateway (if not already configured)

1. Go to the API Gateway console
2. Create a new REST API
3. Create a new resource and method (POST)
4. Set the integration type to Lambda Function
5. Select your Lambda function
6. Deploy the API to a stage
7. Note the API endpoint URL for configuring your TradingView alerts

### 6. Configure TradingView Alerts

Configure TradingView alerts with webhooks pointing to your API Gateway endpoint. Example payload:

```json
{
  "password": "your_webhook_password",
  "action": "long",
  "ticker": "BTC",
  "amountPercent": 50
}
```

## Troubleshooting

If you encounter issues:

1. Check CloudWatch Logs for error messages
2. Verify that your Docker build completed successfully
3. Make sure all required environment variables are set in the Lambda configuration
4. Confirm that the IAM role has the necessary permissions

## Supported Trading Features

This Lambda function supports:

1. Trading perpetual futures (e.g., "CRV-USD") with cross-margin only
2. Maximum allowable leverage for each asset
3. Market orders only (no limit, stop, etc.)
4. Position management logic:
   - If "long" webhook with no long position: Open new long
   - If "long" webhook with existing long: Add to position
   - If "long" webhook with existing short: Reduce short
   - Same logic applies for short positions (vice versa)
   - "close" action closes all positions
5. Webhooks include "amountPercent" to determine how much of available balance to use
