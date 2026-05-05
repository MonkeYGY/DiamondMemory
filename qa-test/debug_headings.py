from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto('http://localhost:5173')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)
    
    # Find all h1, h2, h3 headings
    headings = page.locator('h1, h2, h3')
    print(f'Total headings: {headings.count()}')
    for i in range(min(10, headings.count())):
        tag = page.evaluate(f'() => document.querySelectorAll("h1, h2, h3")[{i}]?.tagName || "?"')
        text = headings.nth(i).text_content().strip()
        print(f'  {tag}: "{text}"')
    
    browser.close()
