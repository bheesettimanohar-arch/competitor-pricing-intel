# ruff: noqa
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

import re
import json
from typing import Any, AsyncGenerator

from google.adk import Workflow, Event, Context
from google.adk.agents import LlmAgent
from google.adk.tools.agent_tool import AgentTool
from google.adk.events import RequestInput
from google.adk.models import Gemini
from google.adk.apps import App
from google.genai import types

from app.config import config

from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters

# Initialize base model
model = Gemini(
    model=config.model,
    retry_options=types.HttpRetryOptions(attempts=3)
)

# -----------------------------------------------------------------------------
# MCP TOOLSETS (Launch the local MCP server)
# -----------------------------------------------------------------------------

scraper_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="uv",
            args=["run", "--link-mode=copy", "python", "app/mcp_server.py"],
        )
    ),
    tool_filter=["get_competitor_price", "get_shipping_cost"]
)

analyst_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="uv",
            args=["run", "--link-mode=copy", "python", "app/mcp_server.py"],
        )
    ),
    tool_filter=["get_internal_cost", "get_stock_level"]
)

# -----------------------------------------------------------------------------
# SUB-AGENTS & AGENT TOOLS
# -----------------------------------------------------------------------------

competitor_scraper_agent = LlmAgent(
    model=model,
    name="competitor_scraper_agent",
    description="Agent to scrape and extract competitor pricing data.",
    instruction="""You are the Competitor Scraper Agent.
Your job is to look up competitor pricing for the requested product.
Use the competitor pricing tools from the MCP server to find competitor price and shipping details.
Return only the competitor price and shipping information found, for example: 'Competitor price for [Product]: $X.XX, shipping: $Y.YY'""",
    tools=[scraper_toolset]
)

pricing_analyst_agent = LlmAgent(
    model=model,
    name="pricing_analyst_agent",
    description="Agent to analyze margins and recommend pricing changes.",
    instruction="""You are the Pricing Analyst Agent.
Your job is to analyze competitor prices against our internal cost, shipping, and margin constraints.
Ensure our profit margin remains above 15% after shipping.
Determine if we should lower our price to match or raise it to gain margin.
Use the MCP tools to check internal cost and stock level details.
Recommend the final adjusted price and state the reason.""",
    tools=[analyst_toolset]
)

scrape_tool = AgentTool(agent=competitor_scraper_agent, skip_summarization=True)
analyze_tool = AgentTool(agent=pricing_analyst_agent, skip_summarization=True)

orchestrator_agent = LlmAgent(
    model=model,
    name="orchestrator_agent",
    description="Orchestrates scraping and pricing analysis.",
    instruction="""You are the Pricing Intelligence Orchestrator.
When the user asks to analyze pricing for a product, you must:
1. Run the competitor_scraper_agent to get the competitor's price.
2. Run the pricing_analyst_agent to get the pricing recommendations.
3. Compare the recommended price with the current price. If the change (increase or decrease) is greater than 20%, you MUST output:
'Recommended price adjustment of X exceeds 20% limit. This adjustment requires human approval.'
Otherwise, output the final recommendation.
State all details (competitor price, cost, current price, new recommended price).""",
    tools=[scrape_tool, analyze_tool],
    output_key="orchestrator_response"
)


# -----------------------------------------------------------------------------
# WORKFLOW GRAPH NODES
# -----------------------------------------------------------------------------

async def security_checkpoint(node_input: Any = None, ctx: Context = None) -> Event:
    """Security node to check for prompt injection and PII."""
    text = str(node_input) if node_input else ""
    
    # 1. PII Scrubbing (emails, credit card numbers)
    email_regex = r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"
    cc_regex = r"\b(?:\d[ -]*?){13,16}\b"
    
    scrubbed_text = text
    scrubbed_email = False
    scrubbed_cc = False
    
    if re.search(email_regex, scrubbed_text):
        scrubbed_text = re.sub(email_regex, "[REDACTED_EMAIL]", scrubbed_text)
        scrubbed_email = True
        
    if re.search(cc_regex, scrubbed_text):
        scrubbed_text = re.sub(cc_regex, "[REDACTED_CC]", scrubbed_text)
        scrubbed_cc = True
        
    # 2. Prompt Injection Detection
    injection_keywords = ["ignore previous instructions", "system prompt", "override system", "jailbreak"]
    detected_injection = False
    for kw in injection_keywords:
        if kw in text.lower():
            detected_injection = True
            break
            
    # 3. Domain-Specific Rule: Prevent scraping request for non-business products
    restricted_keywords = ["weapon", "drug", "illegal", "bomb", "marijuana"]
    restricted_access = False
    for r_kw in restricted_keywords:
        if r_kw in text.lower():
            restricted_access = True
            break

    # Log audit event
    audit_log = {
        "event": "security_checkpoint",
        "scrubbed_email": scrubbed_email,
        "scrubbed_cc": scrubbed_cc,
        "injection_detected": detected_injection,
        "restricted_access": restricted_access
    }
    
    if detected_injection or restricted_access:
        severity = "CRITICAL"
        audit_log["action"] = "blocked"
        print(json.dumps({"severity": severity, "log": audit_log}))
        return Event(route="SECURITY_EVENT", output="[SECURITY ERROR] Access Blocked: Security violation detected.")
    
    severity = "INFO"
    audit_log["action"] = "continue"
    print(json.dumps({"severity": severity, "log": audit_log}))
    
    if ctx:
        ctx.state["temp:scrubbed_input"] = scrubbed_text
    
    return Event(route="CONTINUE", output=scrubbed_text)


def security_event_node(node_input: Any = None) -> Event:
    """Terminal node for security violations."""
    return Event(message=str(node_input) if node_input else "")


def check_approval(node_input: Any = None, ctx: Context = None) -> Event:
    """Checks if the recommendation requires human approval."""
    # Retrieve orchestrator output from state since LLM agents do not set Event.output
    response_text = ctx.state.get("orchestrator_response", "") if ctx else str(node_input) if node_input else ""
    if "requires human approval" in response_text.lower():
        if ctx:
            ctx.state["temp:pending_pricing_proposal"] = response_text
        return Event(route="NEEDS_APPROVAL", output=response_text)
    
    return Event(route="CONTINUE", output=response_text)


async def human_approval_node(node_input: Any = None) -> AsyncGenerator[RequestInput, None]:
    """Yields a RequestInput to pause the workflow and wait for manager approval."""
    yield RequestInput(
        message="[HUMAN ✋] The price adjustment requires manager approval. Please type 'approve' to finalize or 'reject' to cancel:"
    )


def handle_approval_input(node_input: Any = None, ctx: Context = None) -> Event:
    """Processes manager's decision."""
    decision = str(node_input).lower().strip() if node_input else ""
    if "approve" in decision or "yes" in decision:
        proposal = ctx.state.get("temp:pending_pricing_proposal", "Recommended price adjustment approved.") if ctx else "Approved."
        return Event(route="CONTINUE", output=f"Manager Approval Received. {proposal}")
    
    return Event(route="REJECTED", output="Price adjustment rejected by manager. Change cancelled.")


def finalize_pricing(node_input: Any = None) -> Event:
    """Terminal node for finalized pricing."""
    return Event(message=f"Success: {str(node_input) if node_input else ''}")


def reject_pricing(node_input: Any = None) -> Event:
    """Terminal node for rejected pricing."""
    return Event(message=f"Cancelled: {str(node_input) if node_input else ''}")


# -----------------------------------------------------------------------------
# WORKFLOW GRAPH ASSEMBLY
# -----------------------------------------------------------------------------

root_agent = Workflow(
    name="competitor_pricing_workflow",
    edges=[
        ("START", security_checkpoint),
        (security_checkpoint, {
            "CONTINUE": orchestrator_agent,
            "SECURITY_EVENT": security_event_node
        }),
        (orchestrator_agent, check_approval),
        (check_approval, {
            "NEEDS_APPROVAL": human_approval_node,
            "CONTINUE": finalize_pricing
        }),
        (human_approval_node, handle_approval_input),
        (handle_approval_input, {
            "CONTINUE": finalize_pricing,
            "REJECTED": reject_pricing
        })
    ]
)

app = App(
    root_agent=root_agent,
    name="app",
)
