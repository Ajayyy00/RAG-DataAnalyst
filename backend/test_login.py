import asyncio, httpx

async def test():
    async with httpx.AsyncClient(base_url='http://localhost:8001', timeout=30) as c:
        accounts = [
            ('admin@healthcare.com',   'Admin1234!'),
            ('doctor@healthcare.com',  'Doctor1234!'),
            ('analyst@healthcare.com', 'Analyst1234!'),
        ]
        for email, pw in accounts:
            r = await c.post(
                '/api/v1/auth/login',
                data={'username': email, 'password': pw},
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
            )
            if r.status_code == 200:
                tok = r.json()['access_token']
                me  = await c.get('/api/v1/auth/me', headers={'Authorization': 'Bearer ' + tok})
                u   = me.json()
                role  = u.get('role', '?')
                fname = u.get('first_name', '')
                lname = u.get('last_name', '')
                print('  OK   ' + email + '  ->  role=' + role + '  name=' + fname + ' ' + lname)
            else:
                print('  FAIL ' + email + '  ->  ' + str(r.status_code) + ': ' + r.text[:80])

asyncio.run(test())
