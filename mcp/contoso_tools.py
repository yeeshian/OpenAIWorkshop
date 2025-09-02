"""
Contoso Customer Service Tools

This module contains granular functions for interacting with the Contoso customer database.
Each function is designed to be used by both MCP tools and AutoGen agents.
All functions include comprehensive docstrings for AutoGen agent understanding.
"""

import sqlite3
import os
import json
import math
import time
from typing import List, Optional, Dict, Any
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database configuration
DB_PATH = os.getenv("DB_PATH", "data/contoso.db")

def get_db() -> sqlite3.Connection:
    """Get a database connection with row factory."""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

# Safe OpenAI import / dummy embedding
try:
    from openai import AzureOpenAI
    
    _client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
    )
    _emb_model = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
    
    def get_embedding(text: str) -> List[float]:
        text = text.replace("\n", " ")
        return _client.embeddings.create(input=[text], model=_emb_model).data[0].embedding
        
except Exception:
    def get_embedding(text: str) -> List[float]:
        # 1536-d zero vector fallback when creds are missing (tests/dev mode)
        return [0.0] * 1536

def cosine_similarity(vec1, vec2):
    """Calculate cosine similarity between two vectors."""
    dot = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = math.sqrt(sum(a * a for a in vec1))
    norm2 = math.sqrt(sum(b * b for b in vec2))
    return dot / (norm1 * norm2) if norm1 and norm2 else 0.0

# ========================================================================
# CUSTOMER FUNCTIONS
# ========================================================================

async def get_all_customers_async() -> List[Dict[str, Any]]:
    """
    Get a list of all customers with basic information.
    
    Returns:
        List of customer dictionaries containing customer_id, first_name, 
        last_name, email, and loyalty_level
    """
    db = get_db()
    rows = db.execute(
        "SELECT customer_id, first_name, last_name, email, loyalty_level FROM Customers"
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]

async def get_customer_detail_async(customer_id: int) -> Dict[str, Any]:
    """
    Get detailed customer profile including subscriptions.
    
    Args:
        customer_id: The unique identifier for the customer
        
    Returns:
        Customer profile dictionary with personal info and subscriptions list
        
    Raises:
        ValueError: If customer not found
    """
    db = get_db()
    cust = db.execute(
        "SELECT * FROM Customers WHERE customer_id = ?", (customer_id,)
    ).fetchone()
    if not cust:
        db.close()
        raise ValueError(f"Customer {customer_id} not found")
    subs = db.execute(
        "SELECT * FROM Subscriptions WHERE customer_id = ?", (customer_id,)
    ).fetchall()
    db.close()
    result = dict(cust)
    result['subscriptions'] = [dict(s) for s in subs]
    return result

async def get_customer_orders_async(customer_id: int) -> List[Dict[str, Any]]:
    """
    Get all orders placed by a specific customer.
    
    Args:
        customer_id: The unique identifier for the customer
        
    Returns:
        List of order dictionaries with order details and product names
    """
    db = get_db()
    rows = db.execute(
        """
        SELECT o.order_id, o.order_date, p.name as product_name,
               o.amount, o.order_status
        FROM Orders o
        JOIN Products p ON p.product_id = o.product_id
        WHERE o.customer_id = ?
        ORDER BY o.order_date DESC
        """,
        (customer_id,),
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]

# ========================================================================
# SUBSCRIPTION FUNCTIONS
# ========================================================================

async def get_subscription_detail_async(subscription_id: int) -> Dict[str, Any]:
    """
    Get detailed subscription information including invoices and service incidents.
    
    Args:
        subscription_id: The unique identifier for the subscription
        
    Returns:
        Comprehensive subscription details with nested invoices and incidents
        
    Raises:
        ValueError: If subscription not found
    """
    db = get_db()
    sub = db.execute(
        """
        SELECT s.*, p.name AS product_name, p.description AS product_description,
               p.category, p.monthly_fee
        FROM Subscriptions s
        JOIN Products p ON p.product_id = s.product_id
        WHERE s.subscription_id = ?
        """,
        (subscription_id,),
    ).fetchone()
    if not sub:
        db.close()
        raise ValueError("Subscription not found")

    # Get invoices with nested payments
    invoices_rows = db.execute(
        """
        SELECT invoice_id, invoice_date, amount, description, due_date
        FROM Invoices WHERE subscription_id = ?""",
        (subscription_id,),
    ).fetchall()

    invoices = []
    for inv in invoices_rows:
        pay_rows = db.execute(
            "SELECT * FROM Payments WHERE invoice_id = ?", (inv["invoice_id"],)
        ).fetchall()
        total_paid = sum(p["amount"] for p in pay_rows if p["status"] == "successful")
        invoice_dict = dict(inv)
        invoice_dict['payments'] = [dict(p) for p in pay_rows]
        invoice_dict['outstanding'] = max(inv["amount"] - total_paid, 0.0)
        invoices.append(invoice_dict)

    # Get service incidents
    inc_rows = db.execute(
        """
        SELECT incident_id, incident_date, description, resolution_status
        FROM ServiceIncidents
        WHERE subscription_id = ?""",
        (subscription_id,),
    ).fetchall()

    db.close()
    result = dict(sub)
    result['invoices'] = invoices
    result['service_incidents'] = [dict(r) for r in inc_rows]
    return result

async def update_subscription_async(subscription_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update subscription fields like roaming, status, product, etc.
    
    Args:
        subscription_id: The unique identifier for the subscription
        updates: Dictionary of field names and new values to update
        
    Returns:
        Dictionary with subscription_id and list of updated fields
        
    Raises:
        ValueError: If no fields provided or subscription not found
    """
    if not updates:
        raise ValueError("No fields supplied")
    
    # Filter out None values
    data = {k: v for k, v in updates.items() if v is not None}
    if not data:
        raise ValueError("No valid fields to update")
        
    sets = ", ".join(f"{k} = ?" for k in data)
    params = list(data.values()) + [subscription_id]
    
    db = get_db()
    cur = db.execute(f"UPDATE Subscriptions SET {sets} WHERE subscription_id = ?", params)
    db.commit()
    db.close()
    
    if cur.rowcount == 0:
        raise ValueError("Subscription not found")
    
    return {"subscription_id": subscription_id, "updated_fields": list(data.keys())}

async def get_data_usage_async(
    subscription_id: int,
    start_date: str,
    end_date: str,
    aggregate: bool = False,
) -> List[Dict[str, Any]] | Dict[str, Any]:
    """
    Get daily data usage records for a subscription over a date range.
    
    Args:
        subscription_id: The unique identifier for the subscription
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        aggregate: If True, return totals instead of daily records
        
    Returns:
        List of daily usage records or aggregated totals dictionary
    """
    db = get_db()
    rows = db.execute(
        """
        SELECT usage_date, data_used_mb, voice_minutes, sms_count
        FROM DataUsage
        WHERE subscription_id = ?
          AND usage_date BETWEEN ? AND ?
        ORDER BY usage_date
        """,
        (subscription_id, start_date, end_date),
    ).fetchall()
    db.close()
    
    if aggregate:
        total_mb = sum(r["data_used_mb"] for r in rows)
        total_voice = sum(r["voice_minutes"] for r in rows)
        total_sms = sum(r["sms_count"] for r in rows)
        return {
            "subscription_id": subscription_id,
            "start_date": start_date,
            "end_date": end_date,
            "total_mb": total_mb,
            "total_voice_minutes": total_voice,
            "total_sms": total_sms,
        }
    return [dict(r) for r in rows]

# ========================================================================
# BILLING FUNCTIONS
# ========================================================================

async def get_billing_summary_async(customer_id: int) -> Dict[str, Any]:
    """
    Calculate what a customer currently owes across all subscriptions.
    
    Args:
        customer_id: The unique identifier for the customer
        
    Returns:
        Dictionary with total_due amount and breakdown by invoice
    """
    db = get_db()
    inv_rows = db.execute(
        """
        SELECT inv.invoice_id, inv.amount,
               IFNULL(SUM(pay.amount),0) AS paid
        FROM Invoices inv
        LEFT JOIN Payments pay ON pay.invoice_id = inv.invoice_id
                                 AND pay.status='successful'
        WHERE inv.subscription_id IN
            (SELECT subscription_id FROM Subscriptions WHERE customer_id = ?)
        GROUP BY inv.invoice_id
        """,
        (customer_id,),
    ).fetchall()
    db.close()
    
    outstanding = [
        {"invoice_id": r["invoice_id"], "outstanding": max(r["amount"] - r["paid"], 0.0)}
        for r in inv_rows
    ]
    total_due = sum(item["outstanding"] for item in outstanding)
    
    return {"customer_id": customer_id, "total_due": total_due, "invoices": outstanding}

async def get_invoice_payments_async(invoice_id: int) -> List[Dict[str, Any]]:
    """
    Get all payments made against a specific invoice.
    
    Args:
        invoice_id: The unique identifier for the invoice
        
    Returns:
        List of payment records for the invoice
    """
    db = get_db()
    rows = db.execute("SELECT * FROM Payments WHERE invoice_id = ?", (invoice_id,)).fetchall()
    db.close()
    return [dict(r) for r in rows]

async def pay_invoice_async(invoice_id: int, amount: float, method: str = "credit_card") -> Dict[str, Any]:
    """
    Record a payment against an invoice and return the new outstanding balance.
    
    Args:
        invoice_id: The unique identifier for the invoice
        amount: Payment amount to record
        method: Payment method (default: "credit_card")
        
    Returns:
        Dictionary with invoice_id and new outstanding balance
        
    Raises:
        ValueError: If invoice not found
    """
    today = datetime.now().strftime("%Y-%m-%d")
    db = get_db()
    
    # Insert payment record
    db.execute(
        "INSERT INTO Payments(invoice_id, payment_date, amount, method, status) VALUES (?,?,?,?,?)",
        (invoice_id, today, amount, method, "successful"),
    )
    
    # Calculate remaining balance
    inv = db.execute("SELECT amount FROM Invoices WHERE invoice_id = ?", (invoice_id,)).fetchone()
    if not inv:
        db.close()
        raise ValueError("Invoice not found")
        
    paid = db.execute(
        "SELECT SUM(amount) as paid FROM Payments WHERE invoice_id = ? AND status='successful'",
        (invoice_id,),
    ).fetchone()["paid"]
    
    db.commit()
    db.close()
    
    outstanding = max(inv["amount"] - (paid or 0), 0.0)
    return {"invoice_id": invoice_id, "outstanding": outstanding}

# ========================================================================
# SECURITY FUNCTIONS
# ========================================================================

async def get_security_logs_async(customer_id: int) -> List[Dict[str, Any]]:
    """
    Get security events for a customer, newest first.
    
    Args:
        customer_id: The unique identifier for the customer
        
    Returns:
        List of security log entries for the customer
    """
    db = get_db()
    rows = db.execute(
        "SELECT log_id, event_type, event_timestamp, description "
        "FROM SecurityLogs WHERE customer_id = ? ORDER BY event_timestamp DESC",
        (customer_id,),
    ).fetchall()
    db.close()
    return [dict(r) for r in rows]

async def unlock_account_async(customer_id: int) -> Dict[str, str]:
    """
    Unlock a customer account that was locked for security reasons.
    
    Args:
        customer_id: The unique identifier for the customer
        
    Returns:
        Dictionary with success message
        
    Raises:
        ValueError: If no recent lock event found
    """
    db = get_db()
    row = db.execute(
        "SELECT 1 FROM SecurityLogs WHERE customer_id = ? AND event_type = 'account_locked' "
        "ORDER BY event_timestamp DESC LIMIT 1",
        (customer_id,),
    ).fetchone()
    
    if not row:
        db.close()
        raise ValueError("No recent lock event; nothing to do.")
    
    db.execute(
        "INSERT INTO SecurityLogs (customer_id, event_type, event_timestamp, description) "
        "VALUES (?, 'account_unlocked', ?, 'Unlocked via API')",
        (customer_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )
    db.commit()
    db.close()
    
    return {"message": "Account unlocked"}

# ========================================================================
# PRODUCT FUNCTIONS
# ========================================================================

async def get_products_async(category: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    List available products, optionally filtered by category.
    
    Args:
        category: Optional category filter (e.g., "Mobile", "Internet")
        
    Returns:
        List of product dictionaries with details and pricing
    """
    db = get_db()
    if category:
        rows = db.execute("SELECT * FROM Products WHERE category = ?", (category,)).fetchall()
    else:
        rows = db.execute("SELECT * FROM Products").fetchall()
    db.close()
    return [dict(r) for r in rows]

async def get_product_detail_async(product_id: int) -> Dict[str, Any]:
    """
    Get detailed information about a specific product.
    
    Args:
        product_id: The unique identifier for the product
        
    Returns:
        Product details dictionary
        
    Raises:
        ValueError: If product not found
    """
    db = get_db()
    r = db.execute("SELECT * FROM Products WHERE product_id = ?", (product_id,)).fetchone()
    db.close()
    if not r:
        raise ValueError("Product not found")
    return dict(r)

# ========================================================================
# PROMOTION FUNCTIONS
# ========================================================================

async def get_promotions_async() -> List[Dict[str, Any]]:
    """
    Get all active promotions available in the system.
    
    Returns:
        List of promotion dictionaries with details and eligibility criteria
    """
    db = get_db()
    rows = db.execute("SELECT * FROM Promotions").fetchall()
    db.close()
    return [dict(r) for r in rows]

async def get_eligible_promotions_async(customer_id: int) -> List[Dict[str, Any]]:
    """
    Get promotions that a specific customer is eligible for based on loyalty level and dates.
    
    Args:
        customer_id: The unique identifier for the customer
        
    Returns:
        List of eligible promotion dictionaries
        
    Raises:
        ValueError: If customer not found
    """
    db = get_db()
    cust = db.execute("SELECT loyalty_level FROM Customers WHERE customer_id = ?", (customer_id,)).fetchone()
    if not cust:
        db.close()
        raise ValueError("Customer not found")
    
    loyalty = cust["loyalty_level"]
    today = datetime.now().strftime("%Y-%m-%d")
    
    rows = db.execute(
        """
        SELECT * FROM Promotions
        WHERE start_date <= ? AND end_date >= ?
        """,
        (today, today),
    ).fetchall()
    db.close()
    
    eligible = []
    for r in rows:
        crit = r["eligibility_criteria"] or ""
        if f"loyalty_level = '{loyalty}'" in crit or "loyalty_level" not in crit:
            eligible.append(dict(r))
    
    return eligible

# ========================================================================
# SUPPORT FUNCTIONS
# ========================================================================

async def get_support_tickets_async(customer_id: int, open_only: bool = False) -> List[Dict[str, Any]]:
    """
    Get support tickets for a customer, optionally filtered to open tickets only.
    
    Args:
        customer_id: The unique identifier for the customer
        open_only: If True, only return tickets that are not closed
        
    Returns:
        List of support ticket dictionaries
    """
    db = get_db()
    query = "SELECT * FROM SupportTickets WHERE customer_id = ?"
    if open_only:
        query += " AND status != 'closed'"
    rows = db.execute(query, (customer_id,)).fetchall()
    db.close()
    return [dict(r) for r in rows]

async def create_support_ticket_async(
    customer_id: int,
    subscription_id: int,
    category: str,
    priority: str,
    subject: str,
    description: str,
) -> Dict[str, Any]:
    """
    Create a new support ticket for a customer.
    
    Args:
        customer_id: The unique identifier for the customer
        subscription_id: The subscription this ticket relates to
        category: Ticket category (e.g., "Technical", "Billing")
        priority: Priority level (e.g., "High", "Medium", "Low")
        subject: Brief subject line for the ticket
        description: Detailed description of the issue
        
    Returns:
        The created support ticket dictionary
    """
    opened = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    db = get_db()
    cur = db.execute(
        """
        INSERT INTO SupportTickets
        (customer_id, subscription_id, category, opened_at, closed_at,
         status, priority, subject, description, cs_agent)
        VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            customer_id,
            subscription_id,
            category,
            opened,
            None,
            "open",
            priority,
            subject,
            description,
            "AI_Bot",
        ),
    )
    ticket_id = cur.lastrowid
    db.commit()
    row = db.execute("SELECT * FROM SupportTickets WHERE ticket_id = ?", (ticket_id,)).fetchone()
    db.close()
    return dict(row)

# ========================================================================
# KNOWLEDGE BASE FUNCTIONS
# ========================================================================

async def search_knowledge_base_async(query: str, topk: int = 3) -> List[Dict[str, Any]]:
    """
    Semantic search on policy and procedure knowledge documents.
    
    Args:
        query: Natural language search query
        topk: Number of top matching documents to return
        
    Returns:
        List of knowledge document dictionaries with title, type, and content
    """
    query_emb = get_embedding(query)
    db = get_db()
    rows = db.execute("SELECT title, doc_type, content, topic_embedding FROM KnowledgeDocuments").fetchall()
    db.close()
    
    scored = []
    for r in rows:
        try:
            emb = json.loads(r["topic_embedding"])
            sim = cosine_similarity(query_emb, emb)
            scored.append((sim, r))
        except Exception:
            continue
    
    scored.sort(reverse=True, key=lambda x: x[0])
    best = scored[:topk]
    
    return [
        {"title": r["title"], "doc_type": r["doc_type"], "content": r["content"]}
        for sim, r in best
    ]
