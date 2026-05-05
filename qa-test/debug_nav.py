from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://localhost:5173')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)
    
    # Check sidebar nav items
    nav_items = page.locator('.el-menu-item, [class*="nav"], [class*="sidebar"] a, nav a')
    print('Nav items count:', nav_items.count())
    for i in range(min(15, nav_items.count())):
        text = nav_items.nth(i).text_content().strip().replace('\n', ' ')
        print(f'  Nav {i}: "{text}"')
    
    # Specifically find AI对话
    ai_items = page.locator(':has-text("AI")')
    print('\nAI-related items:', ai_items.count())
    for i in range(min(5, ai_items.count())):
        text = ai_items.nth(i).text_content().strip().replace('\n', ' ')
        print(f'  AI {i}: "{text}"')
    
    browser.close()
