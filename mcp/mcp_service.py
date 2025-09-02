from fastmcp import FastMCP  
from fastmcp.server.middleware import Middleware, MiddlewareContext  # added
from typing import List, Optional, Dict, Any  
from pydantic import BaseModel, Field  
import sqlite3, os, json, math, asyncio, logging, time  
from datetime import datetime  
from dotenv import load_dotenv  
from fastmcp.server.middleware import Middleware, MiddlewareContext 
from fastmcp.server.dependencies import get_access_token 
from fastmcp.exceptions import ToolError
# from fastmcp.server.auth import TokenVerifier, AccessToken  
from fastmcp.server.auth.auth import RemoteAuthProvider  
from fastmcp.server.auth.providers.jwt import JWTVerifier  
from fastmcp.server.auth import AccessToken, TokenVerifier
from starlette.requests import Request 
from starlette.responses import JSONResponse
from fastmcp.server.middleware import Middleware, MiddlewareContext  
from fastmcp.server.dependencies import get_http_request, get_access_token
from fastmcp.utilities.logging import get_logger  

# Import common tools
from contoso_tools import *

logger = get_logger("auth.debug")  



logging.basicConfig(level=logging.DEBUG) 
logging.getLogger("FastMCP").setLevel(logging.DEBUG)
logging.getLogger("FastMCP.fastmcp.server.auth.providers.jwt").setLevel(logging.DEBUG)





load_dotenv()  

# ─────────────────────────────  PASSTHROUGH JWT VERIFIER  ─────────────────────  
class PassthroughJWTVerifier(TokenVerifier):
    """
    Passthrough JWT verifier that accepts any token without validation.

    This verifier is designed for development and testing scenarios where you want
    to bypass JWT validation entirely while maintaining the token structure. It
    accepts any token string and returns a default AccessToken with configurable
    claims.

    Use this when:
    - You're developing or testing locally and want to bypass authentication
    - You need to simulate authenticated requests without real tokens
    - You want to test your application logic without JWT complexity

    WARNING: Never use this in production - it accepts ANY token string!
    """

    def __init__(
        self,
        *,
        default_client_id: str = "passthrough-user",
        default_scopes: list[str] | None = None,
        default_claims: dict[str, Any] | None = None,
        required_scopes: list[str] | None = None,
        resource_server_url: str | None = None,
    ):
        """
        Initialize the passthrough token verifier.

        Args:
            default_client_id: Default client ID to return for all tokens
            default_scopes: Default scopes to assign to all tokens
            default_claims: Default claims to include in all tokens
            required_scopes: Required scopes for all tokens (still enforced)
            resource_server_url: Resource server URL for TokenVerifier protocol
        """
        super().__init__(
            resource_server_url=resource_server_url,
            required_scopes=required_scopes,
        )
        
        self.default_client_id = default_client_id
        self.default_scopes = default_scopes or []
        self.default_claims = default_claims or {}
        self.logger = get_logger(__name__)

    async def verify_token(self, token: str) -> AccessToken | None:
        """
        Accept any token and return default access token.
        
        Args:
            token: Any token string (not validated)
            
        Returns:
            AccessToken with default values, or None if required scopes not met
        """
        if not token or not token.strip():
            self.logger.debug("Empty token provided to passthrough verifier")
            return None

        # Check required scopes against default scopes
        if self.required_scopes:
            token_scopes = set(self.default_scopes)
            required_scopes = set(self.required_scopes)
            if not required_scopes.issubset(token_scopes):
                self.logger.debug(
                    "Default scopes don't meet required scopes. Has: %s, Required: %s",
                    token_scopes,
                    required_scopes,
                )
                return None

        # Build claims with defaults
        claims = {
            "sub": self.default_client_id,
            "client_id": self.default_client_id,
            "iss": "passthrough-verifier",
            "iat": int(time.time()),
            "scope": " ".join(self.default_scopes),
            **self.default_claims,
        }

        self.logger.debug(
            "Passthrough verifier accepted token for client %s", 
            self.default_client_id
        )

        return AccessToken(
            token=token,
            client_id=self.default_client_id,
            scopes=self.default_scopes,
            expires_at=None,  # Never expires
            claims=claims,
        )

# ────────────────────────── FastMCP INITIALISATION ──────────────────────  
# Check if authentication should be disabled
DISABLE_AUTH = os.getenv("DISABLE_AUTH", "false").lower() in ("true", "1", "yes", "on")

# Check if passthrough authentication should be used (accepts any token)
USE_PASSTHROUGH_AUTH = os.getenv("USE_PASSTHROUGH_AUTH", "true").lower() in ("true", "1", "yes", "on")

# Configure JWT verification using Entra ID (issuer, audience, JWKS)
AAD_TENANT = os.getenv("AAD_TENANT_ID")
MCP_AUDIENCE = os.getenv("MCP_API_AUDIENCE") 

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")  # set to your public URL  
  
issuer = f"https://login.microsoftonline.com/{AAD_TENANT}/v2.0" if AAD_TENANT else None  
jwks_uri = f"https://login.microsoftonline.com/{AAD_TENANT}/discovery/v2.0/keys" if AAD_TENANT else None  
  
token_verifier = None  
if not DISABLE_AUTH:  
    if USE_PASSTHROUGH_AUTH:
        # Use passthrough verifier that accepts any token
        token_verifier = PassthroughJWTVerifier(
            default_client_id="passthrough-user",
            default_scopes=["query", "security"],  # Grant all needed scopes
            default_claims={"roles": ["query", "security"]},  # Include roles for middleware
        )
    elif jwks_uri and issuer:
        # Use real JWT verification
        token_verifier = JWTVerifier(  
            jwks_uri=jwks_uri,  
            # issuer=issuer,  
            audience=None,  # set if you need audience checking  
            algorithm="RS256",  
        )  
  
auth = None  
if token_verifier and not DISABLE_AUTH:  
    # This publishes resource metadata and makes 401 responses carry WWW-Authenticate  
    auth = RemoteAuthProvider(  
        token_verifier=token_verifier,  
        authorization_servers=[issuer],  # tells clients where auth actually happens  
        resource_server_url=PUBLIC_BASE_URL.rstrip("/") + "/mcp",  # used in WWW-Authenticate and metadata  
        resource_name="Contoso Customer API",  
    )  
  
mcp = FastMCP(  
    name="Contoso Customer API as Tools",  
    instructions=(  
        "All customer, billing and knowledge data is accessible ONLY via the declared "  
        "tools below.  Return values follow the pydanticschemas.  Always call the most "  
        "specific tool that answers the user’s question."  
    ),
    auth=auth,  
) 

##############################################################################  
#                              Pydantic MODELS                               #  
##############################################################################  
class CustomerSummary(BaseModel):  
    customer_id: int  
    first_name: str  
    last_name: str  
    email: str  
    loyalty_level: str  
  
  
class CustomerDetail(BaseModel):  
    customer_id: int  
    first_name: str  
    last_name: str  
    email: str  
    phone: Optional[str]  
    address: Optional[str]  
    loyalty_level: str  
    subscriptions: List[dict]  
  
  
class Payment(BaseModel):  
    payment_id: int  
    payment_date: Optional[str]  
    amount: float  
    method: str  
    status: str  
  
  
class Invoice(BaseModel):  
    invoice_id: int  
    invoice_date: str  
    amount: float  
    description: str  
    due_date: str  
    payments: List[Payment]  
    outstanding: float  
  
  
class ServiceIncident(BaseModel):  
    incident_id: int  
    incident_date: str  
    description: str  
    resolution_status: str  
  
  
class SubscriptionDetail(BaseModel):  
    subscription_id: int  
    product_id: int  
    start_date: str  
    end_date: str  
    status: str  
    roaming_enabled: int  
    service_status: str  
    speed_tier: Optional[str]  
    data_cap_gb: Optional[int]  
    autopay_enabled: int  
    product_name: str  
    product_description: Optional[str]  
    category: Optional[str]  
    monthly_fee: Optional[float]  
    invoices: List[Invoice]  
    service_incidents: List[ServiceIncident]  
  
  
class Promotion(BaseModel):  
    promotion_id: int  
    product_id: int  
    name: str  
    description: str  
    eligibility_criteria: Optional[str]  
    start_date: str  
    end_date: str  
    discount_percent: Optional[int]  
  
  
class KBSearchParams(BaseModel):  
    query: str = Field(..., description="natural lanaguage query")  
    topk: Optional[int] = Field(3, description="Number of top documents to return")  
  
  
class KBDoc(BaseModel):  
    title: str  
    doc_type: str  
    content: str  
  
  
class SecurityLog(BaseModel):  
    log_id: int  
    event_type: str  
    event_timestamp: str  
    description: str  
  
  
class Order(BaseModel):  
    order_id: int  
    order_date: str  
    product_name: str  
    amount: float  
    order_status: str  
  
  
class DataUsageRecord(BaseModel):  
    usage_date: str  
    data_used_mb: int  
    voice_minutes: int  
    sms_count: int  
  
  
class SupportTicket(BaseModel):  
    ticket_id: int  
    subscription_id: int  
    category: str  
    opened_at: str  
    closed_at: Optional[str]  
    status: str  
    priority: str  
    subject: str  
    description: str  
    cs_agent: str  
  
  
class SubscriptionUpdateRequest(BaseModel):  
    roaming_enabled: Optional[int] = None  
    status: Optional[str] = None  
    service_status: Optional[str] = None  
    product_id: Optional[int] = None  
    start_date: Optional[str] = None  
    end_date: Optional[str] = None  
    autopay_enabled: Optional[int] = None  
    speed_tier: Optional[str] = None  
    data_cap_gb: Optional[int] = None  
  
  
# ─── simple arg models ───────────────────────────────────────────────────  
class CustomerIdParam(BaseModel):  
    customer_id: int  
  
  
class SubscriptionIdParam(BaseModel):  
    subscription_id: int  
  
  
class InvoiceIdParam(BaseModel):  
    invoice_id: int  
  
  
# Normalized scope helpers
SECURITY_ROLE = os.getenv("SECURITY_ROLE", "security")
QUERY_ROLE = os.getenv("QUERY_ROLE", "query")


ALLOWED_TENANTS = {t.strip() for t in os.getenv("ALLOWED_TENANTS", (AAD_TENANT or "")).split(",") if t.strip()}

RESTRICTED_TOOLS_REQUIRING_ACCOUNT_SCOPE = {"unlock_account"}  
  
  
  
  
class AuthZMiddleware(Middleware):  
  
    async def on_list_tools(self, context: MiddlewareContext, call_next):  
        tools = await call_next(context)  
  
        # If authentication is disabled, return all tools
        if DISABLE_AUTH:
            return tools
  
        # If there isn't an access token yet (shouldn't happen with auth enabled),  
        # just return the full set.  
        token = get_access_token()  
        if token is None:  
            return tools  
        roles = token.claims["roles"]

        # If the caller has security role, show everything.  
        if SECURITY_ROLE in roles:  
            return tools  
  
        # Otherwise, hide tools that require account scope.  
        filtered = [  
            t for t in tools  
            if t.key not in RESTRICTED_TOOLS_REQUIRING_ACCOUNT_SCOPE  
        ]  
        return filtered  
  
    async def on_call_tool(self, context: MiddlewareContext, call_next):  
        # If authentication is disabled, allow all tool calls
        if DISABLE_AUTH:
            return await call_next(context)
            
        token = get_access_token()  
  
        # With FastMCP auth enabled, missing/invalid tokens are blocked before this point.  
        if token is None:  
            # pass
            raise ToolError("Authentication required")  
        roles = token.claims["roles"]
        tool_name = context.message.name  
  
        # If the caller has account-management scope, allow all tools.  
        if SECURITY_ROLE in roles:    
            return await call_next(context)  
  
        # If they don't have account-management scope, block restricted tools.  
        if tool_name in RESTRICTED_TOOLS_REQUIRING_ACCOUNT_SCOPE:  
            raise ToolError(  
                f"Insufficient authorization to call '{tool_name}'. "  
                f"Requires '{SECURITY_ROLE}'."  
            )  
  
        # All other tools are allowed (including billing-only callers).  
        return await call_next(context) 
# Register middleware
mcp.add_middleware(AuthZMiddleware())


@mcp.custom_route("/mcp/.well-known/oauth-protected-resource", methods=["GET"])  
async def _protected_resource_metadata(request: Request):  
    """  
    Endpoint to return OAuth protected resource metadata.  
    """  
  
    # If authentication is disabled, return 404 as resource is not protected
    if DISABLE_AUTH:
        return JSONResponse({"error": "auth not enabled"}, status_code=404)
  
    # Access the FastMCP server and its auth provider  
    server = request.app.state.fastmcp_server  
    auth = getattr(server, "auth", None)  
  
    if auth is None:  
        return JSONResponse({"error": "auth not configured"}, status_code=404)  
  
    # Resource must exactly match what your clients call (your MCP URL)  
    # Set it via RemoteAuthProvider(..., resource_server_url="https://.../mcp")  
    resource = str(auth.resource_server_url).rstrip("/")  
  
    # Authorization servers; RemoteAuthProvider stores this on the instance  
    auth_servers = getattr(auth, "authorization_servers", []) or []  
    auth_servers = [str(x) for x in auth_servers]  
  
    # Scopes the resource expects (often [])  
    scopes = getattr(auth, "required_scopes", []) or []  
  
    return JSONResponse(  
        {  
            "resource": resource,  
            "authorization_servers": auth_servers,  
            "scopes_supported": scopes,  
        }  
    )  
##############################################################################  
#                               TOOL ENDPOINTS                               #  
##############################################################################  
@mcp.tool(description="List all customers with basic info")  
async def get_all_customers() -> List[CustomerSummary]:  
    data = await get_all_customers_async()
    return [CustomerSummary(**r) for r in data]
  
  
@mcp.tool(description="Get a full customer profile including their subscriptions")  
async def get_customer_detail(params: CustomerIdParam) -> CustomerDetail:  
    data = await get_customer_detail_async(params.customer_id)
    return CustomerDetail(**data)  
  
  
@mcp.tool(  
    description=(  
        "Detailed subscription view → invoices (with payments) + service incidents."  
    )  
)  
async def get_subscription_detail(params: SubscriptionIdParam) -> SubscriptionDetail:  
    data = await get_subscription_detail_async(params.subscription_id)
    
    # Convert nested data to Pydantic models
    invoices = []
    for inv_data in data['invoices']:
        payments = [Payment(**p) for p in inv_data['payments']]
        invoices.append(Invoice(**{**inv_data, 'payments': payments}))
    
    service_incidents = [ServiceIncident(**si) for si in data['service_incidents']]
    
    return SubscriptionDetail(**{**data, 'invoices': invoices, 'service_incidents': service_incidents})  
  
  
@mcp.tool(description="Return invoice‑level payments list")  
async def get_invoice_payments(params: InvoiceIdParam) -> List[Payment]:  
    data = await get_invoice_payments_async(params.invoice_id)
    return [Payment(**r) for r in data]
  
  
@mcp.tool(description="Record a payment for a given invoice and get new outstanding balance")  
async def pay_invoice(invoice_id: int, amount: float, method: str = "credit_card") -> Dict[str, Any]:  
    return await pay_invoice_async(invoice_id, amount, method)
  
  
@mcp.tool(description="Daily data‑usage records for a subscription over a date range")  
async def get_data_usage(  
    subscription_id: int,  
    start_date: str,  
    end_date: str,  
    aggregate: bool = False,  
) -> List[DataUsageRecord] | Dict[str, Any]:  
    result = await get_data_usage_async(subscription_id, start_date, end_date, aggregate)
    if aggregate:
        return result
    return [DataUsageRecord(**r) for r in result]
  
  
@mcp.tool(description="List every active promotion (no filtering)")  
async def get_promotions() -> List[Promotion]:  
    data = await get_promotions_async()
    return [Promotion(**r) for r in data]
  
  
@mcp.tool(  
    description="Promotions *eligible* for a given customer right now "  
    "(evaluates basic loyalty/date criteria)."  
)  
async def get_eligible_promotions(params: CustomerIdParam) -> List[Promotion]:  
    data = await get_eligible_promotions_async(params.customer_id)
    return [Promotion(**r) for r in data]  
  
  
# ─── Knowledge Base Search ───────────────────────────────────────────────  
@mcp.tool(description="Semantic search on policy / procedure knowledge documents")  
async def search_knowledge_base(params: KBSearchParams) -> List[KBDoc]:  
    data = await search_knowledge_base_async(params.query, params.topk)
    return [KBDoc(**r) for r in data]
  
  
# ─── Security Logs ───────────────────────────────────────────────────────  
@mcp.tool(description="Security events for a customer (newest first)")  
async def get_security_logs(params: CustomerIdParam) -> List[SecurityLog]:  
    data = await get_security_logs_async(params.customer_id)
    return [SecurityLog(**r) for r in data]
  
  
# ─── Orders ──────────────────────────────────────────────────────────────  
@mcp.tool(description="All orders placed by a customer")  
async def get_customer_orders(params: CustomerIdParam) -> List[Order]:  
    data = await get_customer_orders_async(params.customer_id)
    return [Order(**r) for r in data]
  
  
# ─── Support Tickets ────────────────────────────────────────────────────  
@mcp.tool(description="Retrieve support tickets for a customer (optionally filter by open status)")  
async def get_support_tickets(  
    customer_id: int,  
    open_only: bool = False,  
) -> List[SupportTicket]:  
    data = await get_support_tickets_async(customer_id, open_only)
    return [SupportTicket(**r) for r in data]
  
  
@mcp.tool(description="Create a new support ticket for a customer")  
async def create_support_ticket(  
    customer_id: int,  
    subscription_id: int,  
    category: str,  
    priority: str,  
    subject: str,  
    description: str,  
) -> SupportTicket:  
    data = await create_support_ticket_async(customer_id, subscription_id, category, priority, subject, description)
    return SupportTicket(**data)
  
  
# ─── Products ────────────────────────────────────────────────────────────  
class Product(BaseModel):  
    product_id: int  
    name: str  
    description: str  
    category: str  
    monthly_fee: float  
  
  
@mcp.tool(description="List / search available products (optional category filter)")  
async def get_products(category: Optional[str] = None) -> List[Product]:  
    data = await get_products_async(category)
    return [Product(**r) for r in data]
  
  
@mcp.tool(description="Return a single product by ID")  
async def get_product_detail(product_id: int) -> Product:  
    data = await get_product_detail_async(product_id)
    return Product(**data)  
  
  
# ─── Update Subscription ────────────────────────────────────────────────  
@mcp.tool(description="Update one or more mutable fields on a subscription.")  
async def update_subscription(subscription_id: int, update: SubscriptionUpdateRequest) -> dict:  
    updates = update.dict(exclude_unset=True)
    return await update_subscription_async(subscription_id, updates)
  
  
# ─── Unlock Account ──────────────────────────────────────────────────────  
@mcp.tool(description="Unlock a customer account locked for security reasons")  
async def unlock_account(params: CustomerIdParam) -> dict:  
    return await unlock_account_async(params.customer_id)
  
  
# ─── Billing summary ─────────────────────────────────────────────────────  
@mcp.tool(description="What does a customer currently owe across all subscriptions?")  
async def get_billing_summary(params: CustomerIdParam) -> Dict[str, Any]:  
    return await get_billing_summary_async(params.customer_id)  
  
  
##############################################################################  
#                                RUN SERVER                                  #  
##############################################################################  
if __name__ == "__main__":  
    asyncio.run(mcp.run_http_async(host="0.0.0.0", port=8000))  