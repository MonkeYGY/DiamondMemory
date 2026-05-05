from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://localhost:5173')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(5000)
    
    # Take screenshot
    page.screenshot(path='/Users/gengyun/Desktop/DiamondMemory/qa-test/screenshots/debug-page.png', full_page=True)
    
    # Get page content for debugging
    body_content = page.evaluate('() => document.body.innerHTML')
    print('Body innerHTML (first 2000 chars):')
    print(body_content[:2000])
    
    # Check for app-root
    app_root = page.locator('#app')
    print('\n#app exists:', app_root.count() > 0)
    if app_root.count() > 0:
        app_html = page.evaluate('() => document.getElementById("app")?.innerHTML || "empty"')
        print('#app innerHTML (first 1000 chars):')
        print(app_html[:1000])
    
    # Check for any rendered Vue components
    all_divs = page.locator('div')
    print('\nTotal div count:', all_divs.count())
    
    # Check for error messages
    errors = page.locator(':has-text("error"), :has-text("Error"), :has-text("failed"), :has-text("连接")')
    print('Elements with error/connection text:', errors.count())
    for i in range(min(5, errors.count())):
        print(f'  Error {i}:', errors.nth(i).text_content().strip()[:100])
    
    browser.close()
