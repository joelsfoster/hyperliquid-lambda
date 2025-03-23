import os
import json
import logging
from decimal import Decimal
import hmac
import hashlib
import base64
from typing import Dict, Any, Optional, List, Tuple

# Import dotenv for .env file loading during local development
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
if os.path.exists(".env"):
    load_dotenv(override=True)

from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger('hyperliquid-lambda')

# Constants for TradingView webhook IP addresses
TV_WEBHOOK_IPS = [
    '52.89.214.238',
    '34.212.75.30',
    '54.218.53.128',
    '52.32.178.7'
]

def validate_webhook_password(event_body: Dict[str, Any]) -> bool:
    """Validate the webhook password from the request body."""
    webhook_password = os.environ.get('WEBHOOK_PASSWORD')
    if not webhook_password:
        logger.error("WEBHOOK_PASSWORD environment variable not set")
        return False
    
    # Get password from the request
    received_password = event_body.get('password')
    if not received_password:
        logger.error("No password provided in webhook payload")
        return False
    
    # Use constant-time comparison to avoid timing attacks
    valid = hmac.compare_digest(webhook_password, received_password)
    if not valid:
        logger.error("Invalid webhook password")
    
    return valid

def validate_source_ip(event: Dict[str, Any]) -> bool:
    """Validate that the request comes from a TradingView IP address."""
    source_ip = event.get('requestContext', {}).get('identity', {}).get('sourceIp')
    if not source_ip:
        logger.error("Source IP not found in event")
        return False
    
    valid = source_ip in TV_WEBHOOK_IPS
    if not valid:
        logger.error(f"IP {source_ip} not in allowed TradingView IPs: {TV_WEBHOOK_IPS}")
    
    return valid

def create_wallet_from_private_key(private_key: str):
    """Create a wallet object from a private key."""
    import eth_account
    return eth_account.Account.from_key(private_key)

def get_all_clients():
    """Creates both Exchange and Info clients from environment variables.
    
    Returns (address, info, exchange) tuple.
    """
    # Get private key from environment
    private_key = os.environ.get('HYPERLIQUID_PRIVATE_KEY')
    
    # Check if we have a private key
    if not private_key:
        logger.error("HYPERLIQUID_PRIVATE_KEY environment variable not set")
        raise ValueError("Wallet not configured. Set HYPERLIQUID_PRIVATE_KEY environment variable.")
    
    # Create wallet from private key
    account = create_wallet_from_private_key(private_key)
    address = account.address
    logger.debug(f"Using wallet address: {address}")
    
    # Check if using mainnet from environment
    use_mainnet_env = os.environ.get('HYPERLIQUID_USE_MAINNET', 'true').lower()
    is_mainnet = use_mainnet_env == 'true'
    logger.debug(f"Using network: {'mainnet' if is_mainnet else 'testnet'}")
    
    base_url = constants.MAINNET_API_URL if is_mainnet else constants.TESTNET_API_URL
    
    # Create the clients
    info = Info(base_url, skip_ws=True)
    exchange = Exchange(account, base_url)
    
    return address, info, exchange

def format_number(num):
    """Format a number to string with precision appropriate for Hyperliquid API."""
    if isinstance(num, str):
        # Already a string, return as is
        return num
    elif isinstance(num, (int, float, Decimal)):
        # Convert numeric types to string
        return str(num)
    elif num is None:
        # Handle None values
        return "0"
    else:
        # For any other type, convert to string
        return str(num)

def close_position_for_asset(asset: str) -> Dict[str, Any]:
    """Close position for a specific asset.
    
    Args:
        asset: Asset symbol (e.g., "BTC")
    
    Returns:
        Dictionary with response details
    """
    # Get clients using the SDK pattern
    address, info, exchange = get_all_clients()
    
    try:
        # Get current positions using the Info client
        user_state = info.user_state(address)
        
        # Find position for the specified asset
        asset_positions = user_state.get('assetPositions', [])
        position_data = None
        
        for asset_position in asset_positions:
            if 'position' in asset_position and asset_position['position'].get('coin') == asset:
                position_data = asset_position['position']
                break
        
        if not position_data:
            logger.info(f"No open position found for {asset} to close")
            return {"status": "success", "message": f"No open position found for {asset} to close"}
        
        # Use the market_close method to close the position
        logger.info(f"Closing existing {asset} position before opening new position in opposite direction")
        response = exchange.market_close(
            coin=asset,
            slippage=0.01  # Allow 1% slippage by default
        )
        
        if response.get('status') == 'ok':
            logger.info(f"Successfully closed {asset} position")
            return {"status": "success", "message": f"Successfully closed {asset} position"}
        else:
            logger.error(f"Failed to close {asset} position: {json.dumps(response, indent=2)}")
            return {"status": "error", "message": f"Failed to close {asset} position"}
    
    except Exception as e:
        logger.error(f"Error closing {asset} position: {str(e)}")
        return {"status": "error", "message": f"Error closing {asset} position: {str(e)}"}

def open_position(asset: str, side: str, percent: int) -> Dict[str, Any]:
    """Open a long or short position.
    
    Args:
        asset: Asset symbol (e.g., "BTC")
        side: "long" or "short"
        percent: Percentage of available USDC balance to use (1-100)
    
    Returns:
        Dictionary with response details
    """
    # Get clients using the SDK pattern
    address, info, exchange = get_all_clients()
    
    # Validate percentage input is within range
    if percent < 1 or percent > 100:
        logger.error(f"Percentage must be between 1 and 100, got {percent}")
        return {"status": "error", "message": f"Percentage must be between 1 and 100, got {percent}"}
    
    try:
        # Convert asset ticker to uppercase for consistency
        asset = asset.upper()
        
        # Get asset metadata to check if it exists and get max leverage
        meta = info.meta()
        
        # Get asset info
        asset_info = next((a for a in meta['universe'] if a['name'] == asset), None)
        if not asset_info:
            logger.error(f"Asset {asset} not found")
            return {"status": "error", "message": f"Asset {asset} not found"}
        
        # Get user state to check USDC balance
        user_state = info.user_state(address)
        
        # Get available USDC balance
        withdrawable_usdc = Decimal(user_state.get('withdrawable', '0'))
        
        if withdrawable_usdc <= 0:
            logger.error("Insufficient balance: no USDC available for trading")
            return {"status": "error", "message": "Insufficient balance: no USDC available for trading"}
        
        # Get current market price for the asset
        market_prices = info.all_mids()
        
        if asset in market_prices:
            current_price = Decimal(str(market_prices[asset]))
            logger.debug(f"Found price for {asset}: {current_price}")
        else:
            # If the asset isn't found by exact name, try to find it in a case-insensitive way
            asset_upper = asset.upper()
            logger.debug(f"Asset {asset} not found, trying {asset_upper}")
            
            if asset_upper in market_prices:
                current_price = Decimal(str(market_prices[asset_upper]))
                logger.debug(f"Found price for {asset_upper}: {current_price}")
            else:
                logger.error(f"Could not get current price for {asset}")
                return {"status": "error", "message": f"Could not get current price for {asset}"}
        
        if current_price <= 0:
            logger.error(f"Invalid price (0 or negative) for {asset}")
            return {"status": "error", "message": f"Invalid price (0 or negative) for {asset}"}
        
        # Use maximum leverage allowed for this asset
        max_leverage = int(asset_info.get('maxLeverage', 10))
        
        # Calculate amount in USD to use based on percentage of withdrawable
        usdc_amount = withdrawable_usdc * Decimal(str(percent)) / Decimal('100')
        logger.debug(f"USDC amount to use: {usdc_amount} (from {withdrawable_usdc} * {percent}%)")
        
        # Calculate position size (in tokens) based on USD amount and current price
        # size = (USD amount × leverage) ÷ price
        size_raw = (usdc_amount * Decimal(str(max_leverage))) / current_price
        logger.debug(f"Calculated size: {size_raw} (from {usdc_amount} * {max_leverage} / {current_price})")
        
        # Handle size precision based on asset type
        # Some assets like XRP require integer values
        if asset in ['XRP', 'DOGE', 'SHIB', 'FARTCOIN']:
            # Use integer values for certain assets
            size = Decimal(str(int(size_raw)))
        else:
            # For assets that trade in decimal values (BTC, ETH, etc.)
            decimal_places = 4
            size = round(size_raw, decimal_places)
        
        # For tiny sizes, ensure we have a minimal position
        if size <= 0:
            logger.error(f"Calculated position size too small. Try increasing the percentage.")
            return {"status": "error", "message": "Calculated position size too small. Try increasing the percentage."}
        
        # Set the leverage to maximum - leverage must be an integer for the API
        int_leverage = max_leverage
        
        # Log the leverage setting attempt
        logger.debug(f"Setting leverage for {asset} to {int_leverage}x")
        
        # Update leverage first as shown in the SDK examples
        leverage_response = exchange.update_leverage(int_leverage, asset)
        
        if leverage_response.get('status') != 'ok':
            logger.warning(f"Leverage setting may have failed: {json.dumps(leverage_response, indent=2)}")
        else:
            logger.debug(f"Successfully set leverage to {int_leverage}x")
        
        # Check if we need to close an existing position in the opposite direction
        user_state = info.user_state(address)
        asset_positions = user_state.get('assetPositions', [])
        
        # Check if there's an existing position for this asset
        for asset_position in asset_positions:
            if 'position' in asset_position and asset_position['position'].get('coin') == asset:
                position = asset_position['position']
                if 'szi' in position:
                    size_val = position['szi']
                    position_size = Decimal(str(size_val))
                    is_long_position = position_size > 0
                    
                    # If we have a position in the opposite direction of what we're trying to open
                    if (side == 'long' and not is_long_position) or (side == 'short' and is_long_position):
                        logger.info(f"Found existing {asset} position in opposite direction. Closing it first.")
                        close_result = close_position_for_asset(asset)
                        
                        if close_result.get('status') != 'success':
                            logger.error(f"Failed to close opposite position: {close_result.get('message')}")
                            return close_result
                        
                        # After closing, we need to refresh user state to get updated balance
                        user_state = info.user_state(address)
                        withdrawable_usdc = Decimal(user_state.get('withdrawable', '0'))
                        
                        # Recalculate the position size with updated balance
                        usdc_amount = withdrawable_usdc * Decimal(str(percent)) / Decimal('100')
                        size_raw = (usdc_amount * Decimal(str(max_leverage))) / current_price
                        
                        # Apply the same size handling logic
                        if asset in ['XRP', 'DOGE', 'SHIB', 'FARTCOIN']:
                            size = Decimal(str(int(size_raw)))
                        else:
                            decimal_places = 4
                            size = round(size_raw, decimal_places)
                        
                        if size <= 0:
                            logger.error(f"Calculated position size too small after closing opposite position.")
                            return {"status": "error", "message": "Calculated position size too small after closing opposite position."}
                break
        
        # Create an order request
        is_buy = (side == 'long')
        
        logger.debug(f"Placing {'buy' if is_buy else 'sell'} order for {size} {asset}")
        
        # Use market_open for all orders as per requirements
        response = exchange.market_open(
            name=asset,
            is_buy=is_buy,
            sz=float(size),
            slippage=0.01  # Allow 1% slippage by default
        )
        
        # Log the full response for debugging
        logger.debug(f"Full market_open response: {json.dumps(response, indent=2)}")
        
        # Check for error in the statuses array
        has_error = False
        error_message = None
        
        # Navigate through response structure to check for errors
        if response.get('status') == 'ok' and 'response' in response:
            response_data = response['response']
            if response_data.get('type') == 'order' and 'data' in response_data:
                order_data = response_data['data']
                if 'statuses' in order_data and len(order_data['statuses']) > 0:
                    for status in order_data['statuses']:
                        if 'error' in status:
                            has_error = True
                            error_message = status['error']
                            logger.error(f"Error from exchange: {error_message}")
                            break
        
        if response.get('status') == 'ok' and not has_error:
            # Extract filled information when available
            filled_size = None
            avg_price = None
            order_id = None
            
            # Navigate through response to find filled information
            if 'response' in response and 'data' in response['response']:
                order_data = response['response']['data']
                if 'statuses' in order_data and len(order_data['statuses']) > 0:
                    status = order_data['statuses'][0]
                    if 'filled' in status:
                        filled = status['filled']
                        filled_size = filled.get('totalSz')
                        avg_price = filled.get('avgPx')
                        order_id = filled.get('oid')
            
            result = {
                "status": "success",
                "message": f"Successfully opened {side} position for {asset}",
                "details": {
                    "asset": asset,
                    "side": side,
                    "size": str(size),
                    "leverage": max_leverage,
                    "usd_value": str(size * current_price),
                }
            }
            
            if filled_size and avg_price:
                result["filled"] = {
                    "size": filled_size,
                    "average_price": avg_price,
                    "order_id": order_id
                }
            
            return result
        elif has_error:
            logger.error(f"Order failed with error: {error_message}")
            return {"status": "error", "message": f"Failed to open position: {error_message}"}
        else:
            logger.error("Unknown error occurred")
            return {"status": "error", "message": "Unknown error occurred"}
    
    except Exception as e:
        logger.error(f"Error opening position: {str(e)}")
        return {"status": "error", "message": f"Error opening position: {str(e)}"}

def close_all_positions() -> Dict[str, Any]:
    """Close all open positions.
    
    Returns:
        Dictionary with response details
    """
    # Get clients using the SDK pattern
    address, info, exchange = get_all_clients()
    
    try:
        # Get current positions using the Info client
        user_state = info.user_state(address)
        asset_positions = user_state.get('assetPositions', [])
        
        if not asset_positions:
            logger.info("No open positions to close")
            return {"status": "success", "message": "No open positions to close"}
        
        logger.info(f"Closing {len(asset_positions)} positions...")
        
        closed_positions = []
        failed_positions = []
        
        for asset_position in asset_positions:
            # Extract position details from the nested structure
            if 'position' in asset_position:
                position = asset_position['position']
                asset = position.get('coin', 'unknown')
                
                # Position size is in 'szi'
                if 'szi' in position:
                    size_val = position['szi']
                    size = Decimal(str(size_val))
                    is_long = size > 0
                    abs_size = abs(size)
                else:
                    # Skip if no size information
                    logger.warning(f"Skipping position with no size information: {json.dumps(position, indent=2)}")
                    continue
            
            # Use the market_close method for each position
            logger.debug(f"Closing {asset} position of size {abs_size}")
            
            # Use market_close following SDK examples
            response = exchange.market_close(
                coin=asset,  # market_close uses coin parameter
                slippage=0.01  # Allow 1% slippage by default
            )
            
            if response.get('status') == 'ok':
                logger.info(f"Closed {asset} position")
                closed_positions.append({
                    "asset": asset,
                    "size": str(abs_size),
                    "side": "long" if is_long else "short"
                })
            else:
                logger.error(f"Failed to close {asset} position: {json.dumps(response, indent=2)}")
                failed_positions.append({
                    "asset": asset,
                    "size": str(abs_size),
                    "side": "long" if is_long else "short",
                    "error": response
                })
        
        return {
            "status": "success" if not failed_positions else "partial",
            "message": f"Closed {len(closed_positions)} positions" + (f", {len(failed_positions)} failed" if failed_positions else ""),
            "closed_positions": closed_positions,
            "failed_positions": failed_positions
        }
    
    except Exception as e:
        logger.error(f"Error closing all positions: {str(e)}")
        return {"status": "error", "message": f"Error closing all positions: {str(e)}"}

def lambda_handler(event, context):
    """AWS Lambda handler for processing TradingView webhooks.
    
    Args:
        event: AWS Lambda event
        context: AWS Lambda context
    
    Returns:
        Dictionary with response details
    """
    logger.info(f"Received event: {json.dumps(event)}")
    
    # For API Gateway proxy integration
    if 'body' in event:
        try:
            body = json.loads(event['body'])
        except json.JSONDecodeError:
            logger.error("Failed to parse request body as JSON")
            return {
                'statusCode': 400,
                'body': json.dumps({"status": "error", "message": "Invalid JSON in request body"})
            }
    else:
        body = event
    
    # Validate the source IP (for API Gateway events)
    if 'requestContext' in event and not validate_source_ip(event):
        logger.error("Request from unauthorized IP address")
        return {
            'statusCode': 403,
            'body': json.dumps({"status": "error", "message": "Unauthorized source IP"})
        }
    
    # Validate the webhook password
    if not validate_webhook_password(body):
        logger.error("Invalid webhook password")
        return {
            'statusCode': 403,
            'body': json.dumps({"status": "error", "message": "Invalid webhook password"})
        }
    
    # Process the webhook based on action type
    action = body.get('action', '').lower()
    asset = body.get('ticker', '')
    percent = int(body.get('amountPercent', 5))  # Default to 5% if not specified
    
    logger.info(f"Processing action: {action} for {asset} with {percent}% of balance")
    
    response = {}
    
    if action == 'long':
        response = open_position(asset, 'long', percent)
    elif action == 'short':
        response = open_position(asset, 'short', percent)
    elif action == 'close':
        response = close_all_positions()
    else:
        logger.error(f"Unknown action: {action}")
        response = {"status": "error", "message": f"Unknown action: {action}"}
    
    # Return response formatted for API Gateway proxy integration
    return {
        'statusCode': 200 if response.get('status') != 'error' else 400,
        'headers': {
            'Content-Type': 'application/json'
        },
        'body': json.dumps(response)
    }

if __name__ == "__main__":
    # This block is only used for local testing and will not run in AWS Lambda
    logger.info("This script is being run directly, not as a Lambda function")
    logger.info("Use local_server.py for local testing with ngrok")
