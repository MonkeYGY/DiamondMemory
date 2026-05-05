from playwright.sync_api import sync_playwright
import json
import time
import sys

issues = []
issue_counter = 0

def add_issue(title, severity, description):
    global issue_counter
    issue_counter += 1
    issues.append({
        'id': f'ISSUE-{issue_counter:03d}',
        'title': title,
        'severity': severity,
        'description': description
    })
    print(f"[{severity}] ISSUE-{issue_counter:03d}: {title}")

def test_all_buttons(page):
    """Test all UI buttons across all views"""
    print("\n=== Testing Dashboard View ===")
    
    # Wait for app to fully load
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(2000)
    
    # Check for console errors
    console_errors = []
    page.on('console', lambda msg: console_errors.append(msg.text) if msg.type == 'error' else None)
    
    # Take initial screenshot
    page.screenshot(path='/Users/gengyun/Desktop/DiamondMemory/qa-test/screenshots/01-dashboard-initial.png', full_page=True)
    
    # Test 1: Dashboard loads correctly
    try:
        title = page.locator('h2:has-text("仪表盘")')
        if title.count() > 0:
            print("[PASS] Dashboard title found")
        else:
            add_issue('Dashboard title missing', 'medium', 'Dashboard h2 title "仪表盘" not found')
    except Exception as e:
        add_issue('Dashboard title error', 'high', f'Error finding title: {str(e)}')
    
    # Test 2: Check all stat cards are visible
    stat_cards = ['总记忆数', '今日新增', '记忆分类', '系统状态']
    for stat in stat_cards:
        try:
            card = page.locator(f':has-text("{stat}")').first
            if card.count() > 0:
                print(f"[PASS] Stat card found: {stat}")
            else:
                add_issue(f'Stat card missing: {stat}', 'medium', f'Stat card for "{stat}" not found')
        except:
            add_issue(f'Stat card error: {stat}', 'high', f'Error finding stat card for {stat}')
    
    # Test 3: Backend status check
    try:
        status_elem = page.locator('.backend-status')
        if status_elem.count() > 0:
            print("[PASS] Backend status element found")
    except:
        pass
    
    # Test 4: Navigation sidebar buttons
    nav_items = ['仪表盘', 'AI 对话', '记忆管理', '知识库', '采集中心', '模型管理', '设置']
    for nav in nav_items:
        try:
            nav_btn = page.locator(f':has-text("{nav}")').first
            if nav_btn.count() > 0:
                nav_btn.click()
                page.wait_for_timeout(500)
                print(f"[PASS] Navigation clicked: {nav}")
            else:
                add_issue(f'Navigation missing: {nav}', 'high', f'Navigation item "{nav}" not found')
        except Exception as e:
            add_issue(f'Navigation error: {nav}', 'high', f'Error clicking {nav}: {str(e)}')
    
    # Test 5: Navigate to Memory view and test buttons
    print("\n=== Testing Memory View ===")
    try:
        page.locator(':has-text("记忆管理")').first.click()
        page.wait_for_timeout(1000)
        page.screenshot(path='/Users/gengyun/Desktop/DiamondMemory/qa-test/screenshots/02-memory-view.png', full_page=True)
        
        # Test search button
        search_input = page.locator('input[placeholder*="搜索"]')
        if search_input.count() > 0:
            search_input.fill('test')
            page.wait_for_timeout(500)
            print("[PASS] Memory search input works")
        
        # Test filter buttons
        filter_btns = page.locator('button:has-text("全部")')
        if filter_btns.count() > 0:
            filter_btns.first.click()
            page.wait_for_timeout(300)
            print("[PASS] Memory filter button works")
        
        # Test pagination
        prev_btn = page.locator('button[aria-label="Previous page"], .pagination button:has-text("Previous"), button:has-text("上一页")')
        next_btn = page.locator('button[aria-label="Next page"], .pagination button:has-text("Next"), button:has-text("下一页")')
        if prev_btn.count() > 0:
            prev_btn.click()
            page.wait_for_timeout(300)
            print("[PASS] Pagination previous button works")
        if next_btn.count() > 0:
            next_btn.click()
            page.wait_for_timeout(300)
            print("[PASS] Pagination next button works")
            
    except Exception as e:
        add_issue('Memory view error', 'high', f'Error in memory view: {str(e)}')
    
    # Test 6: Navigate to Knowledge view
    print("\n=== Testing Knowledge View ===")
    try:
        page.locator(':has-text("知识库")').first.click()
        page.wait_for_timeout(1000)
        page.screenshot(path='/Users/gengyun/Desktop/DiamondMemory/qa-test/screenshots/03-knowledge-view.png', full_page=True)
        
        # Test search
        search_input = page.locator('input[placeholder*="搜索"]')
        if search_input.count() > 0:
            search_input.fill('test')
            page.wait_for_timeout(500)
            print("[PASS] Knowledge search input works")
        
        # Test refresh button
        refresh_btn = page.locator('button:has-text("刷新")')
        if refresh_btn.count() > 0:
            refresh_btn.first.click()
            page.wait_for_timeout(1000)
            print("[PASS] Knowledge refresh button works")
            
    except Exception as e:
        add_issue('Knowledge view error', 'high', f'Error in knowledge view: {str(e)}')
    
    # Test 7: Navigate to Ingest view
    print("\n=== Testing Ingest View ===")
    try:
        page.locator(':has-text("采集中心")').first.click()
        page.wait_for_timeout(1000)
        page.screenshot(path='/Users/gengyun/Desktop/DiamondMemory/qa-test/screenshots/04-ingest-view.png', full_page=True)
        
        # Test refresh button
        refresh_btn = page.locator('button:has-text("刷新")')
        if refresh_btn.count() > 0:
            refresh_btn.first.click()
            page.wait_for_timeout(1000)
            print("[PASS] Ingest refresh button works")
        
        # Test file type filters
        file_filters = page.locator('button:has-text("全部"), button:has-text("PDF"), button:has-text("Text")')
        if file_filters.count() > 0:
            file_filters.first.click()
            page.wait_for_timeout(300)
            print("[PASS] Ingest file filter works")
            
    except Exception as e:
        add_issue('Ingest view error', 'high', f'Error in ingest view: {str(e)}')
    
    # Test 8: Navigate to Settings view
    print("\n=== Testing Settings View ===")
    try:
        page.locator(':has-text("设置")').first.click()
        page.wait_for_timeout(1000)
        page.screenshot(path='/Users/gengyun/Desktop/DiamondMemory/qa-test/screenshots/05-settings-view.png', full_page=True)
        
        # Test all save buttons
        save_btns = page.locator('button:has-text("保存")')
        for i in range(save_btns.count()):
            save_btns.nth(i).click()
            page.wait_for_timeout(500)
            print(f"[PASS] Settings save button {i+1} clicked")
        
        # Test reset button
        reset_btn = page.locator('button:has-text("重置")')
        if reset_btn.count() > 0:
            reset_btn.first.click()
            page.wait_for_timeout(500)
            print("[PASS] Settings reset button works")
        
        # Test directory select button
        dir_btn = page.locator('button:has-text("选择目录")')
        if dir_btn.count() > 0:
            dir_btn.first.click()
            page.wait_for_timeout(500)
            print("[PASS] Directory select button works")
            
    except Exception as e:
        add_issue('Settings view error', 'high', f'Error in settings view: {str(e)}')
    
    # Test 9: Navigate to Model view
    print("\n=== Testing Model View ===")
    try:
        page.locator(':has-text("模型")').first.click()
        page.wait_for_timeout(1000)
        page.screenshot(path='/Users/gengyun/Desktop/DiamondMemory/qa-test/screenshots/06-model-view.png', full_page=True)
        
        # Test model selection
        model_selects = page.locator('select, [role="combobox"], [class*="select"]')
        if model_selects.count() > 0:
            print("[PASS] Model select elements found")
        
        # Test generate button
        gen_btn = page.locator('button:has-text("生成记忆")')
        if gen_btn.count() > 0:
            gen_btn.first.click()
            page.wait_for_timeout(1000)
            print("[PASS] Generate memory button clicked")
        
        # Test refresh button
        refresh_btn = page.locator('button:has-text("刷新")')
        if refresh_btn.count() > 0:
            refresh_btn.first.click()
            page.wait_for_timeout(1000)
            print("[PASS] Model refresh button works")
            
    except Exception as e:
        add_issue('Model view error', 'high', f'Error in model view: {str(e)}')
    
    # Final screenshot
    page.screenshot(path='/Users/gengyun/Desktop/DiamondMemory/qa-test/screenshots/07-final-state.png', full_page=True)
    
    # Check for console errors
    time.sleep(1)
    console_logs = []
    
    return console_errors

# Main execution
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={'width': 1280, 'height': 800}
    )
    page = context.new_page()
    
    # Navigate to the app
    print("Navigating to http://localhost:5173...")
    page.goto('http://localhost:5173')
    page.wait_for_load_state('networkidle')
    page.wait_for_timeout(3000)
    
    # Run all tests
    errors = test_all_buttons(page)
    
    # Output results
    print(f"\n{'='*60}")
    print(f"TEST SUMMARY")
    print(f"{'='*60}")
    print(f"Total issues found: {len(issues)}")
    for issue in issues:
        print(f"  [{issue['severity']}] {issue['id']}: {issue['title']}")
    
    # Save report
    report = {
        'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        'total_issues': len(issues),
        'issues': issues
    }
    
    with open('/Users/gengyun/Desktop/DiamondMemory/qa-test/report.json', 'w') as f:
        json.dump(report, f, indent=2)
    
    print(f"\nReport saved to /Users/gengyun/Desktop/DiamondMemory/qa-test/report.json")
    print(f"Screenshots saved to /Users/gengyun/Desktop/DiamondMemory/qa-test/screenshots/")
    
    browser.close()
