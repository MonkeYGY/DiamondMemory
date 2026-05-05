from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    
    # Listen for all network activity
    page.on('console', lambda msg: print(f'CONSOLE [{msg.type}]: {msg.text}'))
    
    page.goto('http://localhost:5173')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(5000)
    
    # Test backend connection from within the page
    result = page.evaluate('''() => {
        return fetch('http://127.0.0.1:15920/health')
            .then(r => r.json())
            .then(data => ({ success: true, data }))
            .catch(e => ({ success: false, error: e.message }))
    }''')
    print('Direct fetch to backend:', result)
    
    # Test Vite proxy
    result2 = page.evaluate('''() => {
        return fetch('/health')
            .then(r => r.json())
            .then(data => ({ success: true, data }))
            .catch(e => ({ success: false, error: e.message }))
    }''')
    print('Proxy fetch to backend:', result2)
    
    # Take screenshot
    page.screenshot(path='/Users/gengyun/Desktop/DiamondMemory/qa-test/screenshots/current-state.png', full_page=True)
    
    # Check if service disconnected dialog is showing
    dialog = page.locator(':has-text("服务已断开")')
    print('Service disconnected dialog visible:', dialog.count() > 0)
    
    browser.close()
