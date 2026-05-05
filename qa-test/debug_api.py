from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://localhost:5173')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)
    
    # Test health endpoint via proxy
    result = page.evaluate('() => fetch("/health").then(r => r.json()).catch(e => ({error: e.message}))')
    print('Health via proxy:', result)
    
    # Test API endpoint
    result2 = page.evaluate('() => fetch("/api/memories/stats").then(r => r.json()).catch(e => ({error: e.message}))')
    print('Memories stats via proxy:', result2)
    
    # Test /api/knowledge
    result3 = page.evaluate('() => fetch("/api/knowledge").then(r => r.json()).catch(e => ({error: e.message}))')
    print('Knowledge via proxy:', str(result3)[:200])
    
    # Check console logs
    page.on('console', lambda msg: print('CONSOLE:', msg.type, msg.text))
    
    # Check if the app shows the dialog
    dialog_text = page.locator(':has-text("服务已断开")')
    print('Dialog visible:', dialog_text.count())
    
    # Take screenshot
    page.screenshot(path='/Users/gengyun/Desktop/DiamondMemory/qa-test/debug-page.png')
    
    browser.close()
