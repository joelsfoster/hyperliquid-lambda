#!/bin/bash
set -e

# Set your AWS account ID and region
# You'll need to customize these values
AWS_ACCOUNT_ID="351933854076"
AWS_REGION="us-east-2"

# Set repository name and image tag
REPO_NAME="hyperliquid-lambda"
IMAGE_TAG="latest"

# Full ECR repository URI
ECR_REPO_URI="$AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com/$REPO_NAME"

echo "Building Docker image for Lambda deployment..."
# CRITICAL: Using --platform=linux/amd64 and --provenance=false flags to ensure AWS Lambda compatibility
docker build --platform=linux/amd64 --provenance=false -t $REPO_NAME:$IMAGE_TAG .

echo "Build completed with AWS Lambda compatibility flags."

echo "Tagging image for ECR..."
docker tag $REPO_NAME:$IMAGE_TAG $ECR_REPO_URI:$IMAGE_TAG

# Check if AWS CLI is installed
if ! command -v aws &> /dev/null; then
    echo "ERROR: AWS CLI is not installed or not in your PATH"
    echo "Please install the AWS CLI using the instructions at:"
    echo "https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
    echo ""
    echo "After installing AWS CLI, configure it with:"
    echo "aws configure"
    echo ""
    echo "Alternatively, to manually push the Docker image to ECR:"
    echo "1. Get the ECR login command for your terminal:"
    echo "   aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_REPO_URI"
    echo ""
    echo "2. Create the ECR repository (if it doesn't exist):"
    echo "   aws ecr create-repository --repository-name $REPO_NAME --region $AWS_REGION"
    echo ""
    echo "3. Push the image to ECR:"
    echo "   docker push $ECR_REPO_URI:$IMAGE_TAG"
    exit 1
fi

# Login to ECR
echo "Logging in to Amazon ECR..."
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com

# Create the repository if it doesn't exist
echo "Creating ECR repository if it doesn't exist..."
aws ecr describe-repositories --repository-names $REPO_NAME --region $AWS_REGION || aws ecr create-repository --repository-name $REPO_NAME --region $AWS_REGION

# Push the image to ECR
echo "Pushing image to ECR..."
docker push $ECR_REPO_URI:$IMAGE_TAG

echo "Done! Container image is now available at: $ECR_REPO_URI:$IMAGE_TAG"
echo "You can now use this image to deploy to AWS Lambda."
