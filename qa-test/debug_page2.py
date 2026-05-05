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
    content = page.content()
    print('Page title:', page.title())
    print('Page URL:', page.url)
    
    # Check for specific elements
    title = page.locator('h1')
    print('H1 count:', title.count())
    if title.count() > 0:
        print('H1 text:', title.first.text_content())
    
    # Check nav items
    nav_items = page.locator('.nav-item, .sidebar-item, nav a, [role="navigation"] a, .el-menu-item')
    print('Nav items count:', nav_items.count())
    for i in range(min(10, nav_items.count())):
        print(f'  Nav {i}:', nav_items.nth(i).text_content().strip())
    
    # Check stat cards
    cards = page.locator('.stat-card, .stat-item, .el-card, [class*="stat"]')
    print('Stat cards count:', cards.count())
    
    browser.close()
