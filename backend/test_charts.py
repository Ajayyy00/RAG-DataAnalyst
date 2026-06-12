"""
Chart Data Pipeline Verifier
Checks that the data coming from the API maps correctly
to what Recharts needs to render bar/line/pie charts.
"""
import asyncio, httpx, json

async def verify():
    async with httpx.AsyncClient(base_url='http://localhost:8001', timeout=90) as c:
        r = await c.post('/api/v1/auth/login',
            data={'username': 'admin@healthcare.com', 'password': 'Admin1234!'},
            headers={'Content-Type': 'application/x-www-form-urlencoded'})
        token = r.json()['access_token']
        H = {'Authorization': 'Bearer ' + token}

        tests = [
            ('Top 5 diagnoses by frequency',      'bar'),
            ('Average LOS by department',          'bar'),
            ('Monthly encounters last 6 months',   'line'),
            ('Patient breakdown by gender',        'pie'),
        ]

        print('=' * 70)
        for question, expected in tests:
            r2 = await c.post('/api/v1/chat/query',
                json={'question': question,
                      'options': {'include_sql': True, 'chart_auto': True}},
                headers=H)
            d = r2.json()

            cols    = d.get('results', {}).get('columns', [])
            rows    = d.get('results', {}).get('rows', [])[:3]
            chart   = d.get('chart', {}) or {}
            ctype   = chart.get('type', 'none')
            x_key   = chart.get('x_key')
            y_key   = chart.get('y_key')
            series  = chart.get('series_keys', [])

            # Simulate what Chat.jsx does
            def to_num(v):
                if v is None or v == '': return v
                try: n = float(v); return int(n) if n == int(n) else n
                except: return v

            chart_data = []
            for row in (d.get('results', {}).get('rows', []) or []):
                obj = {}
                for i, col in enumerate(cols):
                    v = row[i] if i < len(row) else None
                    obj[col] = to_num(v) if isinstance(v, str) else v
                chart_data.append(obj)

            # Verify chart_data is correct for Recharts
            if chart_data and x_key and (y_key or series):
                sample = chart_data[0]
                x_ok  = x_key in sample
                y_ok  = (y_key in sample) or any(k in sample for k in series)
                vals  = [sample.get(y_key or (series[0] if series else ''))]
                num_ok = all(isinstance(v, (int, float)) for v in vals if v is not None)

                status = 'OK ' if (x_ok and y_ok) else 'ERR'
                print(f'  {status}  [{ctype:7s}]  {question[:40]:<42}')
                print(f'         x_key={x_key!r:20s}  y_key={y_key!r}  series={series}')
                print(f'         sample_x={str(sample.get(x_key))[:25]!r:28s}  '
                      f'sample_y={str(sample.get(y_key or (series[0] if series else "")))!r}')
                print(f'         numeric_y={num_ok}  rows={len(chart_data)}')
                if not x_ok: print(f'         ERROR: x_key {x_key!r} not in {list(sample.keys())}')
                if not y_ok: print(f'         ERROR: y_key {y_key!r} not in {list(sample.keys())}')
            else:
                print(f'  ???  [{ctype:7s}]  {question[:40]:<42}  NO CHART DATA')
            print()

        print('=' * 70)
        print('All checks done.')

asyncio.run(verify())
