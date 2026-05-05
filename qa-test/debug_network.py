from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    # Listen for all requests and responses
    page.on('request', lambda req: print(f'REQUEST: {req.method} {req.url}'))
    page.on('response', lambda res: print(f'RESPONSE: {res.status} {res.url}'))
    page.on('console', lambda msg: print(f'CONSOLE [{msg.type}]: {msg.text}'))
    page.on('pageerror', lambda err: print(f'PAGE ERROR: {err}'))
    
    page.goto('http://localhost:5173')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(5000)
    
    print('\n=== DONE ===')
    browser.close()
