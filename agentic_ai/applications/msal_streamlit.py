import streamlit as st, msal, os  
  
def login(scope: str) -> str:  
    authority = os.getenv("AUTHORITY") or f"https://login.microsoftonline.com/{os.getenv('AAD_TENANT_ID') or os.getenv('TENANT_ID')}"  
    client_id = os.getenv("CLIENT_ID") or os.getenv("AZURE_AD_CLIENT_ID")  
    if not client_id:  
        raise RuntimeError("CLIENT_ID (app registration) must be set")  
  
    cache = msal.SerializableTokenCache()  
    app = msal.PublicClientApplication(client_id, authority=authority, token_cache=cache)  
  
    # Try silent first if we have any account cached  
    accounts = app.get_accounts()  
    if accounts:  
        result = app.acquire_token_silent([scope], account=accounts[0])  
        if result and "access_token" in result:  
            return result["access_token"]  
  
    # Device code flow for Streamlit  
    flow = app.initiate_device_flow(scopes=[scope])  
    if "user_code" not in flow:  
        raise RuntimeError("Failed to create device flow")  
    st.info(f"Use code {flow['user_code']} at {flow['verification_uri']} to sign in")  
    st.write("")  
    result = app.acquire_token_by_device_flow(flow)  
    if not result or "access_token" not in result:  
        raise RuntimeError(result.get("error_description", "Login failed"))  
    return result["access_token"]