from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    # Listen for console messages
    page.on('console', lambda msg: print(f'CONSOLE [{msg.type}]: {msg.text}'))
    page.on('pageerror', lambda err: print(f'PAGE ERROR: {err}'))
    
    page.goto('http://localhost:5173')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(5000)
    
    print('Done waiting. Page title:', page.title())
    
    # Take screenshot
    page.screenshot(path='/Users/gengyun/Desktop/DiamondMemory/qa-test/screenshots/debug-page.png', full_page=True)
    
    browser.close()
