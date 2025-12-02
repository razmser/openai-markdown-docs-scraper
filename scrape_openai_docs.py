#!/usr/bin/env python3
"""
Script to scrape OpenAI documentation and convert to markdown.
Downloads pages once and caches them locally for iterative parsing.
Supports multiple pages with different structures.
"""

import os
import re
import requests
from bs4 import BeautifulSoup
from pathlib import Path
import html2text
from urllib.parse import urlparse

try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


# URLs to scrape with their output names
PAGES_TO_SCRAPE = [
    {
        "url": "https://platform.openai.com/docs/api-reference/responses?lang=curl",
        "name": "responses",
    },
    {
        "url": "https://platform.openai.com/docs/api-reference/responses-streaming?lang=curl",
        "name": "responses-streaming",
    },
    {
        "url": "https://platform.openai.com/docs/api-reference/conversations?lang=curl",
        "name": "conversations",
    },
    {
        "url": "https://platform.openai.com/docs/api-reference/chat?lang=curl",
        "name": "chat",
    },
    {
        "url": "https://platform.openai.com/docs/api-reference/chat-streaming?lang=curl",
        "name": "chat-streaming",
    },
]

# Directories for output
SCRAPED_DIR = Path("scraped")
DOCS_DIR = Path("docs")


def download_page_with_playwright(url: str, cache_file: Path) -> str:
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
        try:
            response = page.goto(url, wait_until="domcontentloaded", timeout=60000)
            if response:
                print(f"Page loaded with status: {response.status}")
            else:
                print("Warning: No response object returned from page.goto()")
        except Exception as e:
            print(f"Error during page navigation: {e}")
            raise
        
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
        print("Waiting for page content to load...")
        try:
            page.wait_for_timeout(5000)  # Initial wait for React to start rendering
            
            # Try to wait for content indicators
            selectors_to_try = [
                'h1',  # Main heading
                'h2',  # Section headings
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
                page.wait_for_timeout(10000)
            
        except Exception as e:
            print(f"Warning while waiting for content: {e}")
        
        # Expand all "Show properties" and "Show possible types" buttons
        print("Expanding all collapsible sections...")
        try:
            max_expansion_rounds = 10
            total_expanded = 0
            
            for round_num in range(max_expansion_rounds):
                expand_buttons = page.query_selector_all('button.param-expand-button')
                
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
                        button.scroll_into_view_if_needed()
                        page.wait_for_timeout(50)
                        button.click()
                        total_expanded += 1
                        page.wait_for_timeout(300)
                    except Exception as e:
                        continue
                
                page.wait_for_timeout(1000)
            
            page.wait_for_timeout(2000)
            print(f"Expansion complete. Total buttons expanded: {total_expanded}")
        except Exception as e:
            print(f"Warning while expanding sections: {e}")
        
        # Final wait
        page.wait_for_timeout(3000)
        
        # Get the final rendered content
        content = page.content()
        
        if len(content.strip()) < 100:
            print(f"Warning: Page content is very short ({len(content)} chars)")
            print(f"Page title: {page.title()}")
            print(f"Page URL: {page.url}")
        
        browser.close()
    
    cache_file.write_text(content, encoding='utf-8')
    print(f"Page cached to {cache_file}")
    
    return content


def download_page(url: str, cache_file: Path) -> str:
    """Download the page if not cached, otherwise return cached content."""
    if cache_file.exists():
        print(f"Using cached page from {cache_file}")
        return cache_file.read_text(encoding='utf-8')
    
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
            raise requests.exceptions.HTTPError("403 Forbidden. Page requires JavaScript rendering.")
    
    response.raise_for_status()
    
    content = response.text
    cache_file.write_text(content, encoding='utf-8')
    print(f"Page cached to {cache_file}")
    
    return content


def create_html2text_converter():
    """Create and configure html2text converter."""
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = False
    h.body_width = 0  # Don't wrap lines
    h.unicode_snob = True
    h.escape_snob = True
    h.ignore_emphasis = False
    h.skip_internal_links = False
    return h


def fix_links(text):
    """Convert relative links to absolute."""
    text = re.sub(r'\]\(/docs/([^)]+)\)', r'](https://platform.openai.com/docs/\1)', text)
    text = re.sub(r'\]\(/guides/([^)]+)\)', r'](https://platform.openai.com/docs/guides/\1)', text)
    return text


def process_code_element(code_elem, include_title=False, code_sample_container=None):
    """Process a code/pre element, removing line numbers and returning markdown.
    
    If include_title=True and code_sample_container is provided, will look for
    a code-sample-title and include it as a header.
    """
    if not code_elem:
        return None
    
    from copy import copy
    code_copy = copy(code_elem)
    
    # Remove line number spans
    for line_num in code_copy.find_all('span', class_='react-syntax-highlighter-line-number'):
        line_num.decompose()
    
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
    
    # Heuristic language detection
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
    
    result = f"```{lang}\n{code_text}\n```"
    
    # Check for title if requested
    if include_title and code_sample_container:
        title_elem = code_sample_container.find('div', class_='code-sample-title')
        if title_elem:
            title = title_elem.get_text(strip=True)
            if title:
                result = f"### {title}\n\n{result}"
    
    return result


def build_param_hierarchy(main_content):
    """Build param ID hierarchy for depth calculation."""
    all_param_rows = main_content.find_all('div', class_='param-row')
    all_param_ids = set()
    for row in all_param_rows:
        param_id = row.get('id', '')
        if param_id:
            all_param_ids.add(param_id)
    
    def get_parent_id_from_structure(row_id):
        if not row_id:
            return None
        parts = row_id.split('-')
        for i in range(len(parts) - 1, 0, -1):
            potential_parent = '-'.join(parts[:i])
            if potential_parent in all_param_ids and potential_parent != row_id:
                return potential_parent
        return None
    
    def get_nesting_depth(row_id):
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
    
    return all_param_ids, get_parent_id_from_structure, get_nesting_depth


def param_row_to_markdown(row, get_nesting_depth, h, base_heading_level=4):
    """Convert a single param-row to markdown.
    
    Top-level params (depth 0) use headings (H4 by default).
    All nested params use indented bullet lists.
    """
    param_id = row.get('id', '')
    depth = get_nesting_depth(param_id) if param_id else 0
    
    header = row.find('div', class_='param-row-header')
    if not header:
        return ""
    
    # Get param name/title
    param_name_elem = header.find('div', class_='param-name')
    param_title_elem = header.find('div', class_='param-title')
    
    if param_name_elem:
        name = param_name_elem.get_text(strip=True)
    elif param_title_elem:
        name = param_title_elem.get_text(strip=True)
    else:
        return ""
    
    # Get type
    param_type_elem = header.find('div', class_='param-type')
    param_type = param_type_elem.get_text(strip=True) if param_type_elem else ""
    
    # Get optional/required
    param_optl = header.find('div', class_='param-optl')
    param_reqd = header.find('div', class_='param-reqd')
    optl_text = ""
    if param_optl:
        optl_text = "Optional"
    elif param_reqd:
        optl_text = "Required"
    
    # Get deprecated
    param_depr = header.find('div', class_='param-depr')
    depr_text = "Deprecated" if param_depr else ""
    
    # Get default
    param_default = header.find('div', class_='param-default')
    default_text = param_default.get_text(strip=True) if param_default else ""
    
    # Build header parts
    header_parts = [name]
    if param_type:
        header_parts.append(param_type)
    if optl_text:
        header_parts.append(optl_text)
    if depr_text:
        header_parts.append(depr_text)
    if default_text:
        header_parts.append(default_text)
    
    # Top-level params use headings, nested params use bullet lists
    if depth == 0:
        heading_prefix = '#' * base_heading_level
        header_line = f"{heading_prefix} {' - '.join(header_parts)}"
        indent = ""
        desc_indent = ""
    else:
        # Nested params use bullet lists with indentation
        indent = "  " * (depth - 1)
        header_line = f"{indent}- **{' - '.join(header_parts)}**"
        desc_indent = indent + "  "
    
    # Get description
    param_desc = row.find('div', class_='param-desc')
    desc_md = ""
    if param_desc:
        # Process code samples first
        code_samples = param_desc.find_all('div', class_='code-sample')
        code_blocks = []
        for code_sample in code_samples:
            pre = code_sample.find('pre')
            if pre:
                code_elem = pre.find('code')
                if code_elem:
                    for line_num in code_elem.find_all('span', class_='react-syntax-highlighter-line-number'):
                        line_num.decompose()
                    
                    code_text = code_elem.get_text()
                    lang = 'json'
                    code_class = code_elem.get('class', [])
                    for cls in code_class:
                        if cls.startswith('language-'):
                            lang = cls.replace('language-', '')
                            break
                    
                    code_blocks.append(f"```{lang}\n{code_text.strip()}\n```")
            
            code_sample.decompose()
        
        desc_md = h.handle(str(param_desc)).strip()
        desc_md = fix_links(desc_md)
        desc_md = desc_md.replace('\\_', '_').replace('\\(', '(').replace('\\)', ')')
        
        for code_block in code_blocks:
            desc_md += f"\n\n{code_block}"
        
        # Indent description for nested params
        if depth > 0:
            desc_lines = desc_md.split('\n')
            desc_md = '\n'.join(f"{desc_indent}{line}" if line.strip() else line for line in desc_lines)
    
    return f"{header_line}\n{desc_md}\n" if desc_md else f"{header_line}\n"


def process_param_table_recursive(table_elem, get_nesting_depth, h, seen_ids, base_heading_level=4):
    """Process a param-table and all its nested param-rows."""
    lines = []
    
    for child in table_elem.children:
        if not hasattr(child, 'name') or not child.name:
            continue
        
        if child.name == 'div' and 'param-row' in child.get('class', []):
            param_id = child.get('id', '')
            if param_id and param_id not in seen_ids:
                seen_ids.add(param_id)
                lines.append(param_row_to_markdown(child, get_nesting_depth, h, base_heading_level))
                
                # Process nested param-tables
                nested_tables = child.find_all('div', class_='param-table', recursive=False)
                for nested_table in nested_tables:
                    lines.extend(process_param_table_recursive(nested_table, get_nesting_depth, h, seen_ids, base_heading_level))
        
        elif child.name == 'div' and 'param-table' in child.get('class', []):
            lines.extend(process_param_table_recursive(child, get_nesting_depth, h, seen_ids, base_heading_level))
    
    return lines


def parse_streaming_page(soup, h):
    """Parse streaming events page structure (div.section with div.endpoint)."""
    markdown_lines = []
    
    main_content = soup.find('main')
    if not main_content:
        return None
    
    # Find api-ref container
    api_ref = main_content.find('div', class_='api-ref')
    if not api_ref:
        return None
    
    # Build param hierarchy
    _, _, get_nesting_depth = build_param_hierarchy(main_content)
    
    # Clean up
    for nav in main_content.find_all(['nav', 'aside']):
        nav.decompose()
    for script in main_content(["script", "style", "noscript"]):
        script.decompose()
    
    # Find main title (first h2 in first section.md)
    first_section = api_ref.find('div', class_='section')
    if first_section:
        h2 = first_section.find('h2')
        if h2:
            markdown_lines.append(f"# {h2.get_text(strip=True)}\n")
            
            # Find intro text
            intro = first_section.find('div', class_='docs-markdown-content')
            if intro:
                intro_md = h.handle(str(intro)).strip()
                intro_md = fix_links(intro_md)
                intro_md = intro_md.replace('\\_', '_').replace('\\(', '(').replace('\\)', ')')
                markdown_lines.append(intro_md + "\n")
    
    # Process each event section
    sections = api_ref.find_all('div', class_='section', recursive=False)
    
    for section in sections:
        # Skip first section (intro) if no endpoint div
        endpoint_div = section.find('div', class_='endpoint')
        if not endpoint_div:
            continue
        
        # Get section heading
        h2 = section.find('h2')
        if h2:
            markdown_lines.append(f"## {h2.get_text(strip=True)}\n")
        
        # Process section-left (contains description and params)
        section_left = endpoint_div.find('div', class_='section-left')
        if section_left:
            # Description
            desc_div = section_left.find('div', class_='docs-markdown-content')
            if desc_div:
                desc_md = h.handle(str(desc_div)).strip()
                desc_md = fix_links(desc_md)
                desc_md = desc_md.replace('\\_', '_').replace('\\(', '(').replace('\\)', ')')
                markdown_lines.append(desc_md + "\n")
            
            # Process param-tables
            seen_ids = set()
            param_tables = section_left.find_all('div', class_='param-table', recursive=False)
            if param_tables:
                markdown_lines.append("### Parameters\n")
                for table in param_tables:
                    lines = process_param_table_recursive(table, get_nesting_depth, h, seen_ids)
                    markdown_lines.extend(lines)
        
        # Process section-right (code examples)
        section_right = endpoint_div.find('div', class_='section-right')
        if section_right:
            # Find code-sample divs to get titles
            code_samples = section_right.find_all('div', class_='code-sample')
            for code_sample in code_samples:
                pre = code_sample.find('pre')
                if pre:
                    code_elem = pre.find('code') or pre
                    code_md = process_code_element(code_elem, include_title=True, code_sample_container=code_sample)
                    if code_md:
                        markdown_lines.append(f"{code_md}\n")
    
    if not markdown_lines:
        return None
    
    markdown = '\n'.join(markdown_lines)
    markdown = re.sub(r'\n{3,}', '\n\n', markdown)
    return markdown.strip()


def parse_endpoint_page(soup, h):
    """Parse regular endpoint page structure (endpoint-content or param-section based)."""
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
        return h.handle(str(soup))
    
    # Clean up
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
    
    # Build param hierarchy
    _, _, get_nesting_depth = build_param_hierarchy(main_content)
    
    def process_param_section(section_elem, base_heading_level=4):
        """Process a param-section and its nested param-tables."""
        lines = []
        
        section_heading = section_elem.find('h4')
        if section_heading:
            lines.append(f"### {section_heading.get_text(strip=True)}\n")
        
        seen_ids = set()
        main_table = section_elem.find('div', class_='param-table', recursive=False)
        if main_table:
            lines.extend(process_param_table_recursive(main_table, get_nesting_depth, h, seen_ids, base_heading_level))
        
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
            for elem in section:
                if hasattr(elem, 'name'):
                    h2 = elem.find('h2') if elem.name != 'h2' else elem
                    if h2:
                        markdown_lines.append(f"## {h2.get_text(strip=True)}\n")
                    
                    param_sections = elem.find_all('div', class_='param-section') if elem.name != 'div' else [elem] if 'param-section' in elem.get('class', []) else elem.find_all('div', class_='param-section')
                    for ps in param_sections:
                        lines = process_param_section(ps)
                        markdown_lines.extend(lines)
                    
                    # Find code-sample divs to get titles
                    code_samples = elem.find_all('div', class_='code-sample')
                    if code_samples:
                        for code_sample in code_samples:
                            pre = code_sample.find('pre')
                            if pre:
                                code_elem = pre.find('code') or pre
                                code_md = process_code_element(code_elem, include_title=True, code_sample_container=code_sample)
                                if code_md:
                                    markdown_lines.append(f"{code_md}\n")
                    else:
                        # Fallback to finding pre directly
                        for pre in elem.find_all('pre'):
                            code_elem = pre.find('code') or pre
                            code_md = process_code_element(code_elem)
                            if code_md:
                                markdown_lines.append(f"{code_md}\n")
        else:
            h2 = section.find('h2')
            if h2:
                markdown_lines.append(f"## {h2.get_text(strip=True)}\n")
            
            method_elem = section.find('span', class_='http-method')
            url_elem = section.find('span', class_='http-url') or section.find('code')
            if method_elem and url_elem:
                markdown_lines.append(f"{method_elem.get_text(strip=True)} {url_elem.get_text(strip=True)}\n")
            
            desc = section.find('div', class_='endpoint-desc') or section.find('p')
            if desc:
                desc_md = h.handle(str(desc)).strip()
                desc_md = fix_links(desc_md)
                markdown_lines.append(f"{desc_md}\n")
            
            param_sections = section.find_all('div', class_='param-section')
            for ps in param_sections:
                lines = process_param_section(ps)
                markdown_lines.extend(lines)
            
            # Find code-sample divs to get titles
            code_samples = section.find_all('div', class_='code-sample')
            if code_samples:
                for code_sample in code_samples:
                    pre = code_sample.find('pre')
                    if pre:
                        code_elem = pre.find('code') or pre
                        code_md = process_code_element(code_elem, include_title=True, code_sample_container=code_sample)
                        if code_md:
                            markdown_lines.append(f"{code_md}\n")
            else:
                # Fallback to finding pre directly
                for pre in section.find_all('pre'):
                    code_elem = pre.find('code') or pre
                    code_md = process_code_element(code_elem)
                    if code_md:
                        markdown_lines.append(f"{code_md}\n")
    
    # Fallback if no endpoint sections found
    if not endpoint_sections:
        param_sections = main_content.find_all('div', class_='param-section')
        for ps in param_sections:
            lines = process_param_section(ps)
            markdown_lines.extend(lines)
    
    markdown = '\n'.join(markdown_lines)
    markdown = re.sub(r'\n{3,}', '\n\n', markdown)
    
    return markdown.strip()


def parse_openai_docs(html_content: str) -> str:
    """Parse OpenAI docs HTML and convert to markdown.
    
    Automatically detects page structure and uses appropriate parser.
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    h = create_html2text_converter()
    
    # Detect page type based on structure
    main = soup.find('main')
    if main:
        api_ref = main.find('div', class_='api-ref')
        if api_ref:
            # Check if it's a streaming-style page (sections with endpoints)
            sections = api_ref.find_all('div', class_='section', recursive=False)
            has_endpoint_divs = any(s.find('div', class_='endpoint') for s in sections)
            if has_endpoint_divs:
                result = parse_streaming_page(soup, h)
                if result:
                    return result
    
    # Fall back to endpoint page parser
    return parse_endpoint_page(soup, h)


def process_single_page(page_config: dict, force_download: bool = False):
    """Download and parse a single page."""
    url = page_config["url"]
    name = page_config["name"]
    
    cache_file = SCRAPED_DIR / f"{name}.html"
    output_file = DOCS_DIR / f"{name}.md"
    
    print(f"\n{'='*60}")
    print(f"Processing: {name}")
    print(f"URL: {url}")
    print(f"{'='*60}")
    
    # Remove cache if force download
    if force_download and cache_file.exists():
        cache_file.unlink()
        print(f"Removed existing cache: {cache_file}")
    
    # Download or load cached page
    html_content = download_page(url, cache_file)
    
    # Parse and convert to markdown
    print("Parsing HTML and converting to markdown...")
    markdown = parse_openai_docs(html_content)
    
    # Save markdown
    output_file.write_text(markdown, encoding='utf-8')
    print(f"Markdown saved to {output_file}")
    
    # Preview
    print(f"\nPreview (first 500 characters):")
    print("-" * 50)
    print(markdown[:500])
    print("-" * 50)
    
    return markdown


def main():
    # Ensure directories exist
    SCRAPED_DIR.mkdir(exist_ok=True)
    DOCS_DIR.mkdir(exist_ok=True)
    
    print("OpenAI Documentation Scraper")
    print(f"Scraped HTML will be saved to: {SCRAPED_DIR}/")
    print(f"Markdown files will be saved to: {DOCS_DIR}/")
    
    # Process all configured pages
    for page_config in PAGES_TO_SCRAPE:
        try:
            process_single_page(page_config)
        except Exception as e:
            print(f"\nError processing {page_config['name']}: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*60)
    print("All pages processed!")
    print("="*60)


if __name__ == "__main__":
    main()
