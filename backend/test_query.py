import asyncio
import httpx
from pprint import pprint

async def test_query(question):
    print(f"\n--- Testing Query: {question} ---")
    async with httpx.AsyncClient() as client:
        # Assuming we can hit the endpoint without full auth locally if we mock it, or we need auth?
        # Let's check if the backend requires authentication for /api/v1/chat/query.
        from app.core.security import create_access_token
        from app.config import get_settings
        import uuid
        
        # Hardcode the known admin user ID or just generate a token for admin@healthcare.com
        # Assuming sub is user id. Let's just run a quick query to get the admin user ID
        # For testing, we just need a valid token.
        async with httpx.AsyncClient() as client:
            token = create_access_token({"sub": "admin@healthcare.com", "role": "admin"}) # actually create_access_token expects user ID in sub typically
            # wait, backend expects user ID in sub. Let me just use a fake UUID or get it from DB.
            from app.db.session import AsyncSessionLocal
            from sqlalchemy import text
            async with AsyncSessionLocal() as db:
                result = await db.execute(text("SELECT id FROM users WHERE email = 'admin@healthcare.com'"))
                admin_id = result.scalar()
                
            token = create_access_token({"sub": str(admin_id), "role": "admin"})
            headers = {"Authorization": f"Bearer {token}"}
            
            req_data = {
                "question": question,
                "options": {"include_sql": True, "chart_auto": True, "include_insights": True}
            }
            
            resp = await client.post("http://localhost:8001/api/v1/chat/query", json=req_data, headers=headers, timeout=60.0)
            if resp.status_code != 200:
                print("Query failed:", resp.text)
                return
                
            data = resp.json()
            print("\nSQL:")
            print(data["sql"]["generated"] if data.get("sql") else "No SQL returned")
            
            print("\nResults shape:")
            results = data.get("results")
            if results:
                print(f"Columns: {results['columns']}")
                print(f"Row count: {results['row_count']}")
                if results['rows']:
                    print(f"First row: {results['rows'][0]}")
            
            print("\nChart Config:")
            pprint(data.get("chart"))
            
            print("\nInsights:")
            pprint(data.get("insights"))

async def main():
    await test_query("Readmission trends last 6 months")
    await test_query("Average LOS by department")
    await test_query("Top 5 diagnoses")

if __name__ == "__main__":
    asyncio.run(main())
