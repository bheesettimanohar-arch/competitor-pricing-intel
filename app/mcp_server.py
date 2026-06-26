# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("CompetitorPricingServer")

@mcp.tool()
def get_competitor_price(product_name: str) -> str:
    """Fetch competitor pricing details for a product.
    
    Args:
        product_name: The name of the product.
    """
    p = product_name.lower()
    if "ultra" in p:
        return "Competitor price for UltraWidget Pro: $150.00"
    return "Competitor price for standard product: $80.00"

@mcp.tool()
def get_internal_cost(product_name: str) -> str:
    """Fetch internal cost information and current price.
    
    Args:
        product_name: The name of the product.
    """
    p = product_name.lower()
    if "ultra" in p:
        return "Internal cost for UltraWidget Pro: $100.00. Current price: $120.00"
    return "Internal cost for standard product: $50.00. Current price: $70.00"

@mcp.tool()
def get_stock_level(product_name: str) -> str:
    """Fetch stock levels for a product.
    
    Args:
        product_name: The name of the product.
    """
    p = product_name.lower()
    if "ultra" in p:
        return "Stock Level: 15 units available."
    return "Stock Level: 120 units available."

@mcp.tool()
def get_shipping_cost(product_name: str) -> str:
    """Fetch shipping cost for a product.
    
    Args:
        product_name: The name of the product.
    """
    p = product_name.lower()
    if "ultra" in p:
        return "Shipping Cost: $15.00"
    return "Shipping Cost: $5.00"

if __name__ == "__main__":
    mcp.run(transport="stdio")
