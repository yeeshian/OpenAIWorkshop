This chapter explain about MCP design.
talks about following topics:
1. MCP Security: basic security and multi-tenant security with APIM integration
2. Agentic MCP: intelligent MCP 
3. Advanced features such as progress update 
## MCP Server Architecture
```mermaid
flowchart TD  
    %% Client
    A[User / External Client] -->|HTTP Request| RAP
    %% Auth Layer
    subgraph Auth[Authentication Layer]
        direction TB  
        PAS[PassthroughJWTVerifier]  
        JWT[JWTVerifier]  
        RAP[RemoteAuthProvider]  
        RAP --> PAS
        RAP --> JWT
    end
    %% Middleware
    subgraph MW[Middleware Layer]
        AZ[AuthZMiddleware]
    end
    RAP --> AZ
    %% Tools Grouped
    subgraph Tools[Tool Endpoints]
        direction TB
        subgraph CustomerTools[Customer Management]
            T1[get_all_customers]
            T2[get_customer_detail]
            T11[get_customer_orders]
        end
  
        subgraph SubscriptionTools[Subscription & Billing]
            T3[get_subscription_detail]  
            T4[get_invoice_payments]  
            T5[pay_invoice]  
            T6[get_data_usage]  
            T16[update_subscription]
            T18[get_billing_summary]
        end
  
        subgraph PromoTools[Promotions & Products]
            T7[get_promotions]  
            T8[get_eligible_promotions]  
            T14[get_products]
            T15[get_product_detail]  
        end  
  
        subgraph SupportTools[Support & Security]
            T10[get_security_logs]  
            T12[get_support_tickets]  
            T13[create_support_ticket]
            T17[unlock_account]  
        end  
  
        subgraph KBTools[Knowledge Base]
            T9[search_knowledge_base]  
        end
    end  
  
    %% Data Layer  
    subgraph Data[Data Layer]
        DB[(Database / Async Data Sources)]  
    end  
  
    %% Flow  
    AZ --> Tools  
    Tools -->|Fetch / Store Data| DB  
```