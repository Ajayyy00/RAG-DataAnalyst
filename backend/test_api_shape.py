import asyncio, httpx, json

async def test():
    async with httpx.AsyncClient(base_url='http://localhost:8001', timeout=60) as c:
        # Login
        r = await c.post('/api/v1/auth/login',
            data={'username': 'admin@healthcare.com', 'password': 'Admin1234!'},
            headers={'Content-Type': 'application/x-www-form-urlencoded'})
        token = r.json()['access_token']
        H = {'Authorization': 'Bearer ' + token}

        # Run a bar chart query
        r2 = await c.post('/api/v1/chat/query',
            json={'question': 'Top 5 diagnoses by frequency',
                  'options': {'include_sql': True, 'include_insights': True, 'chart_auto': True}},
            headers=H)
        d = r2.json()

        print('=== TOP-LEVEL KEYS ===')
        print(list(d.keys()))

        print('\n=== SQL section ===')
        print(json.dumps(d.get('sql'), indent=2))

        print('\n=== RESULTS section ===')
        res = d.get('results', {})
        print('  columns:', res.get('columns'))
        print('  row_count:', res.get('row_count'))
        print('  rows (first 3):', res.get('rows', [])[:3])

        print('\n=== CHART section ===')
        print(json.dumps(d.get('chart'), indent=2))

        print('\n=== INSIGHT_REPORT summary ===')
        report = d.get('insight_report') or {}
        print('  summary:', str(report.get('summary',''))[:100])
        print('  trends count:', len(report.get('trends', [])))
        print('  recs count:', len(report.get('recommendations', [])))

asyncio.run(test())
