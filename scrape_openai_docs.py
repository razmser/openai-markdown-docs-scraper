#!/usr/bin/env python3
"""
Script to scrape OpenAI documentation and convert to markdown.
Downloads the page once and caches it locally for iterative parsing.
"""

import os
import re
import requests
from bs4 import BeautifulSoup
from pathlib import Path
import html2text

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


def download_page_with_playwright(url: str, cache_file: str = "cached_page.html") -> str:
    """Download the page using Playwright (handles JavaScript/Cloudflare)."""
    print(f"Downloading page with Playwright from {url}...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()
        
        # Navigate
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # Wait for Cloudflare challenge to complete
        max_wait = 30  # seconds
        wait_interval = 2  # seconds
        waited = 0
        
        while waited < max_wait:
            content = page.content()
            # Check if we've passed Cloudflare
            if ("Just a moment" in content or "Enable JavaScript" in content or 
                "Waiting for platform.openai.com" in content):
                print(f"Waiting for Cloudflare challenge... ({waited}/{max_wait}s)")
                page.wait_for_timeout(wait_interval * 1000)
                waited += wait_interval
            else:
                print(f"Cloudflare challenge passed after {waited} seconds")
                break
        
        # Now wait for React app to load the actual content
        # Look for common content selectors in OpenAI docs
        print("Waiting for page content to load...")
        try:
            # Wait for the main content area to be populated
            # OpenAI docs use various selectors - try multiple approaches
            page.wait_for_timeout(5000)  # Initial wait for React to start rendering
            
            # Try to wait for content indicators
            selectors_to_try = [
                'h1',  # Main heading
                '[data-testid]',  # Test IDs
                'article',
                'main h1',
                'main h2',
            ]
            
            content_loaded = False
            for selector in selectors_to_try:
                try:
                    page.wait_for_selector(selector, timeout=10000, state='visible')
                    print(f"Found content indicator: {selector}")
                    content_loaded = True
                    break
                except:
                    continue
            
            if not content_loaded:
                print("No specific content selectors found, waiting additional time...")
                page.wait_for_timeout(10000)  # Extra wait for dynamic content
            
        except Exception as e:
            print(f"Warning while waiting for content: {e}")
        
        # Expand all "Show properties" and "Show possible types" buttons
        # Need to iterate multiple times because nested buttons only appear after parent expansion
        print("Expanding all collapsible sections...")
        try:
            max_expansion_rounds = 10  # Maximum rounds to prevent infinite loops
            total_expanded = 0
            
            for round_num in range(max_expansion_rounds):
                # Find all expand buttons (re-query each round to find newly visible buttons)
                expand_buttons = page.query_selector_all('button.param-expand-button')
                
                # Count collapsed buttons
                collapsed_buttons = []
                for button in expand_buttons:
                    try:
                        aria_expanded = button.get_attribute('aria-expanded')
                        if aria_expanded == 'false':
                            collapsed_buttons.append(button)
                    except:
                        continue
                
                if not collapsed_buttons:
                    print(f"Round {round_num + 1}: All sections expanded. Total expanded: {total_expanded}")
                    break
                
                print(f"Round {round_num + 1}: Found {len(collapsed_buttons)} collapsed sections, expanding...")
                
                for button in collapsed_buttons:
                    try:
                        # Scroll button into view to ensure it's clickable
                        button.scroll_into_view_if_needed()
                        page.wait_for_timeout(50)
                        button.click()
                        total_expanded += 1
                        # Wait for content to render
                        page.wait_for_timeout(300)
                    except Exception as e:
                        # Some buttons might not be clickable, continue
                        continue
                
                # Wait for all expanded content to render before next round
                page.wait_for_timeout(1000)
            
            # Final wait for all expanded content to render
            page.wait_for_timeout(2000)
            print(f"Expansion complete. Total buttons expanded: {total_expanded}")
        except Exception as e:
            print(f"Warning while expanding sections: {e}")
        
        # Final wait for any remaining dynamic content
        page.wait_for_timeout(3000)
        
        # Get the final rendered content
        content = page.content()
        
        browser.close()
    
    cache_path = Path(cache_file)
    cache_path.write_text(content, encoding='utf-8')
    print(f"Page cached to {cache_file}")
    
    return content


def download_page(url: str, cache_file: str = "cached_page.html") -> str:
    """Download the page if not cached, otherwise return cached content."""
    cache_path = Path(cache_file)
    
    if cache_path.exists():
        print(f"Using cached page from {cache_file}")
        return cache_path.read_text(encoding='utf-8')
    
    # Try Playwright first if available (handles JavaScript)
    if PLAYWRIGHT_AVAILABLE:
        try:
            return download_page_with_playwright(url, cache_file)
        except Exception as e:
            print(f"Playwright download failed: {e}")
            print("Falling back to requests...")
    
    # Fallback to requests
    print(f"Downloading page from {url}...")
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
        'Referer': 'https://platform.openai.com/',
    }
    session = requests.Session()
    session.headers.update(headers)
    response = session.get(url, timeout=30)
    
    if response.status_code != 200:
        print(f"Warning: Got status code {response.status_code}")
        if response.status_code == 403:
            print("\nError: Page requires JavaScript (Cloudflare protection)")
            print("Please install Playwright: pip install playwright && playwright install chromium")
            raise requests.exceptions.HTTPError(f"403 Forbidden. Page requires JavaScript rendering.")
    
    response.raise_for_status()
    
    content = response.text
    cache_path.write_text(content, encoding='utf-8')
    print(f"Page cached to {cache_file}")
    
    return content


def parse_openai_docs(html_content: str) -> str:
    """Parse OpenAI docs HTML and convert to markdown."""
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Initialize html2text converter for non-param content
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = False
    h.body_width = 0  # Don't wrap lines
    h.unicode_snob = True
    h.escape_snob = True
    h.ignore_emphasis = False
    h.skip_internal_links = False
    
    # Find the main content area
    main_content = soup.find('main')
    
    if not main_content:
        main_content = soup.find('article')
        if not main_content:
            body = soup.find('body')
            if body:
                all_divs = body.find_all(['div', 'section', 'article'])
                if all_divs:
                    main_content = max(all_divs, key=lambda x: len(x.get_text(strip=True)))
    
    if not main_content:
        return h.handle(html_content)
    
    # Remove navigation/sidebar elements
    for nav in main_content.find_all(['nav', 'aside']):
        nav.decompose()
    
    for elem in main_content.find_all(['ul', 'ol']):
        links = elem.find_all('a')
        if len(links) > 10:
            api_ref_links = sum(1 for link in links if '/docs/api-reference/' in link.get('href', ''))
            if api_ref_links > 5:
                elem.decompose()
    
    for script in main_content(["script", "style", "noscript"]):
        script.decompose()
    
    # Collect all param IDs for hierarchy calculation
    all_param_rows = main_content.find_all('div', class_='param-row')
    all_param_ids = set()
    for row in all_param_rows:
        param_id = row.get('id', '')
        if param_id:
            all_param_ids.add(param_id)
    
    def get_parent_id_from_structure(row_id):
        """Get parent ID by analyzing the ID structure."""
        if not row_id:
            return None
        parts = row_id.split('-')
        for i in range(len(parts) - 1, 0, -1):
            potential_parent = '-'.join(parts[:i])
            if potential_parent in all_param_ids and potential_parent != row_id:
                return potential_parent
        return None
    
    def get_nesting_depth(row_id):
        """Calculate nesting depth based on ID hierarchy."""
        depth = 0
        current_id = row_id
        while True:
            parent_id = get_parent_id_from_structure(current_id)
            if parent_id:
                depth += 1
                current_id = parent_id
            else:
                break
        return depth
    
    def fix_links(text):
        """Convert relative links to absolute."""
        text = re.sub(r'\]\(/docs/([^)]+)\)', r'](https://platform.openai.com/docs/\1)', text)
        text = re.sub(r'\]\(/guides/([^)]+)\)', r'](https://platform.openai.com/docs/guides/\1)', text)
        return text
    
    def process_code_element(code_elem):
        """Process a code/pre element, removing line numbers and returning markdown."""
        if not code_elem:
            return None
        
        # Clone the element to avoid modifying the original
        from copy import copy
        code_copy = copy(code_elem)
        
        # Remove line number spans
        for line_num in code_copy.find_all('span', class_='react-syntax-highlighter-line-number'):
            line_num.decompose()
        
        # Get the code text
        code_text = code_copy.get_text().strip()
        if not code_text:
            return None
        
        # Detect language from class
        lang = 'text'
        code_class = code_elem.get('class', [])
        for cls in code_class:
            if cls.startswith('language-'):
                lang = cls.replace('language-', '')
                break
        
        # Also check parent pre for language hints
        if lang == 'text':
            if 'curl ' in code_text or code_text.strip().startswith('curl'):
                lang = 'bash'
            elif 'import ' in code_text and ('openai' in code_text.lower() or 'from ' in code_text):
                if 'from "openai"' in code_text or 'from \'openai\'' in code_text or 'require(' in code_text:
                    lang = 'javascript'
                else:
                    lang = 'python'
            elif code_text.strip().startswith('{') or code_text.strip().startswith('['):
                lang = 'json'
        
        return f"```{lang}\n{code_text}\n```"
    
    def param_row_to_markdown(row, base_heading_level=4):
        """Convert a single param-row to markdown with correct heading level."""
        param_id = row.get('id', '')
        depth = get_nesting_depth(param_id) if param_id else 0
        
        # For depths beyond H6, we'll use indentation to show nesting
        heading_level = min(base_heading_level + depth, 6)  # Cap at H6
        extra_depth = max(0, (base_heading_level + depth) - 6)  # How many levels beyond H6
        heading_prefix = '#' * heading_level
        indent = '  ' * extra_depth  # Indent for deep nesting
        
        # Get param info from the header row only (not from nested children)
        header = row.find('div', class_='param-row-header')
        if not header:
            return ""
        
        # Get param name/title
        # Prefer param-name (actual field name like "input") over param-title (display title like "Text input")
        param_name_elem = header.find('div', class_='param-name')
        param_title_elem = header.find('div', class_='param-title')
        
        if param_name_elem:
            name = param_name_elem.get_text(strip=True)
        elif param_title_elem:
            name = param_title_elem.get_text(strip=True)
        else:
            return ""
        
        # Get type from header only
        param_type_elem = header.find('div', class_='param-type')
        param_type = param_type_elem.get_text(strip=True) if param_type_elem else ""
        
        # Get optional/required from header only
        param_optl = header.find('div', class_='param-optl')
        param_reqd = header.find('div', class_='param-reqd')
        optl_text = ""
        if param_optl:
            optl_text = "Optional"
        elif param_reqd:
            optl_text = "Required"
        
        # Get default from header only
        param_default = header.find('div', class_='param-default')
        default_text = param_default.get_text(strip=True) if param_default else ""
        
        # Build header
        header_parts = [name]
        if param_type:
            header_parts.append(param_type)
        if optl_text:
            header_parts.append(optl_text)
        if default_text:
            header_parts.append(default_text)
        
        # For deep nesting (beyond H6), use bullet point with indentation
        if extra_depth > 0:
            header_line = f"{indent}- **{' - '.join(header_parts)}**"
        else:
            header_line = f"{heading_prefix} {' - '.join(header_parts)}"
        
        # Get description
        param_desc = row.find('div', class_='param-desc')
        desc_md = ""
        if param_desc:
            # Process code samples first - extract and convert them properly
            code_samples = param_desc.find_all('div', class_='code-sample')
            code_blocks = []
            for code_sample in code_samples:
                # Find the pre/code element
                pre = code_sample.find('pre')
                if pre:
                    code_elem = pre.find('code')
                    if code_elem:
                        # Remove line number spans
                        for line_num in code_elem.find_all('span', class_='react-syntax-highlighter-line-number'):
                            line_num.decompose()
                        
                        # Get the code text
                        code_text = code_elem.get_text()
                        
                        # Detect language from class
                        lang = 'json'
                        code_class = code_elem.get('class', [])
                        for cls in code_class:
                            if cls.startswith('language-'):
                                lang = cls.replace('language-', '')
                                break
                        
                        code_blocks.append((code_sample, f"```{lang}\n{code_text.strip()}\n```"))
                
                # Remove the code sample from the description for now
                code_sample.decompose()
            
            # Convert the rest of the description
            desc_md = h.handle(str(param_desc)).strip()
            desc_md = fix_links(desc_md)
            # Clean up escaped characters
            desc_md = desc_md.replace('\\_', '_').replace('\\(', '(').replace('\\)', ')')
            
            # Add code blocks back
            for _, code_block in code_blocks:
                desc_md += f"\n\n{code_block}"
            
            # Add indentation to description for deep nesting
            if extra_depth > 0:
                desc_lines = desc_md.split('\n')
                desc_md = '\n'.join(f"{indent}  {line}" if line.strip() else line for line in desc_lines)
        
        return f"{header_line}\n{desc_md}\n" if desc_md else f"{header_line}\n"
    
    def process_param_section(section_elem, base_heading_level=4):
        """Process a param-section and its nested param-tables."""
        lines = []
        
        # Find section heading
        section_heading = section_elem.find('h4')
        if section_heading:
            lines.append(f"### {section_heading.get_text(strip=True)}\n")
        
        # Process param-rows in order
        # We need to walk the DOM in document order, processing each param-row
        def process_element(elem, seen_ids):
            result = []
            
            if elem.name == 'div' and 'param-row' in elem.get('class', []):
                param_id = elem.get('id', '')
                if param_id and param_id not in seen_ids:
                    seen_ids.add(param_id)
                    result.append(param_row_to_markdown(elem, base_heading_level))
                    
                    # Process nested param-table if present (children of this row)
                    nested_tables = elem.find_all('div', class_='param-table', recursive=False)
                    for table in nested_tables:
                        for child in table.children:
                            if hasattr(child, 'name'):
                                result.extend(process_element(child, seen_ids))
            elif elem.name == 'div' and 'param-table' in elem.get('class', []):
                for child in elem.children:
                    if hasattr(child, 'name'):
                        result.extend(process_element(child, seen_ids))
            
            return result
        
        # Find the main param-table
        seen_ids = set()
        main_table = section_elem.find('div', class_='param-table', recursive=False)
        if main_table:
            for child in main_table.children:
                if hasattr(child, 'name'):
                    lines.extend(process_element(child, seen_ids))
        
        return lines
    
    # Build markdown output
    markdown_lines = []
    
    # Find and process main title
    main_title = main_content.find('h1')
    if main_title:
        markdown_lines.append(f"# {main_title.get_text(strip=True)}\n")
    
    # Process intro/description before first endpoint
    intro_elems = []
    for elem in main_content.children:
        if hasattr(elem, 'name'):
            if elem.name == 'h1':
                continue
            # Stop at first endpoint section
            if elem.find('h2') or (elem.name == 'h2'):
                break
            intro_elems.append(elem)
    
    if intro_elems:
        intro_html = ''.join(str(e) for e in intro_elems)
        intro_md = h.handle(intro_html).strip()
        intro_md = fix_links(intro_md)
        intro_md = intro_md.replace('\\_', '_').replace('\\(', '(').replace('\\)', ')')
        markdown_lines.append(intro_md + "\n")
    
    # Process each endpoint section
    endpoint_sections = main_content.find_all('div', class_='endpoint-content')
    if not endpoint_sections:
        # Fallback: look for sections with h2
        endpoint_sections = []
        current_section = []
        for elem in main_content.children:
            if hasattr(elem, 'name'):
                if elem.name == 'h2' or elem.find('h2'):
                    if current_section:
                        endpoint_sections.append(current_section)
                    current_section = [elem]
                elif current_section:
                    current_section.append(elem)
        if current_section:
            endpoint_sections.append(current_section)
    
    for section in endpoint_sections:
        if isinstance(section, list):
            # Process list of elements
            for elem in section:
                if hasattr(elem, 'name'):
                    h2 = elem.find('h2') if elem.name != 'h2' else elem
                    if h2:
                        markdown_lines.append(f"## {h2.get_text(strip=True)}\n")
                    
                    # Process param-sections
                    param_sections = elem.find_all('div', class_='param-section') if elem.name != 'div' else [elem] if 'param-section' in elem.get('class', []) else elem.find_all('div', class_='param-section')
                    for ps in param_sections:
                        lines = process_param_section(ps)
                        markdown_lines.extend(lines)
                    
                    # Process code examples
                    for pre in elem.find_all('pre'):
                        code_elem = pre.find('code') or pre
                        code_md = process_code_element(code_elem)
                        if code_md:
                            markdown_lines.append(f"{code_md}\n")
        else:
            # Process endpoint-content div
            h2 = section.find('h2')
            if h2:
                markdown_lines.append(f"## {h2.get_text(strip=True)}\n")
            
            # Process URL/method
            method_elem = section.find('span', class_='http-method')
            url_elem = section.find('span', class_='http-url') or section.find('code')
            if method_elem and url_elem:
                markdown_lines.append(f"{method_elem.get_text(strip=True)} {url_elem.get_text(strip=True)}\n")
            
            # Process description
            desc = section.find('div', class_='endpoint-desc') or section.find('p')
            if desc:
                desc_md = h.handle(str(desc)).strip()
                desc_md = fix_links(desc_md)
                markdown_lines.append(f"{desc_md}\n")
            
            # Process param-sections
            param_sections = section.find_all('div', class_='param-section')
            for ps in param_sections:
                lines = process_param_section(ps)
                markdown_lines.extend(lines)
            
            # Process code examples
            for pre in section.find_all('pre'):
                code_elem = pre.find('code') or pre
                code_md = process_code_element(code_elem)
                if code_md:
                    markdown_lines.append(f"{code_md}\n")
    
    # If no endpoint sections found, fall back to processing all param-sections
    if not endpoint_sections:
        param_sections = main_content.find_all('div', class_='param-section')
        for ps in param_sections:
            lines = process_param_section(ps)
            markdown_lines.extend(lines)
    
    # Join and clean up
    markdown = '\n'.join(markdown_lines)
    
    # Clean up multiple blank lines
    markdown = re.sub(r'\n{3,}', '\n\n', markdown)
    
    # Store param data for reference (needed by some post-processing)
    param_row_data = {}
    param_hierarchy = {}
    for row in all_param_rows:
        param_id = row.get('id', '')
        if param_id:
            param_name_elem = row.find('div', class_='param-name')
            param_title_elem = row.find('div', class_='param-title')
            if param_title_elem:
                param_name = param_title_elem.get_text(strip=True)
            elif param_name_elem:
                param_name = param_name_elem.get_text(strip=True)
            else:
                continue
            
            depth = get_nesting_depth(param_id)
            parent_id = get_parent_id_from_structure(param_id)
            
            param_row_data[param_name] = {
                'id': param_id,
                'html': str(row),
                'depth': depth,
                'parent_id': parent_id,
                'title': param_name,
                'name': param_name
            }
            param_hierarchy[param_id] = {
                'name': param_name,
                'depth': depth,
                'parent_id': parent_id
            }
    
    # Return the markdown - skip most of the old post-processing
    return markdown.strip()


def main():
    url = "https://platform.openai.com/docs/api-reference/responses/object?lang=curl"
    cache_file = "cached_page.html"
    output_file = "openai_docs.md"
    
    # Download or load cached page
    html_content = download_page(url, cache_file)
    
    # Parse and convert to markdown
    print("Parsing HTML and converting to markdown...")
    markdown = parse_openai_docs(html_content)
    
    # Save markdown
    Path(output_file).write_text(markdown, encoding='utf-8')
    print(f"Markdown saved to {output_file}")
    
    # Print first 500 chars for preview
    print("\nPreview (first 500 characters):")
    print("-" * 50)
    print(markdown[:500])
    print("-" * 50)


if __name__ == "__main__":
    main()
