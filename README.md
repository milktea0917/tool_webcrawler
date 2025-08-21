# Tool: WebCrawler

An easy-to-use tool for crawling web links.  
It can also serve as a basic web crawler template for GPT development.

---

## How to Use

### 1. Base Usage

python webcrawler.py --web <website_url>


> `<website_url>`: the target website you want to crawl.

---

### 2. Custom Options

- **Depth**: Limit crawling depth  
- **Max Pages**: Maximum number of pages to crawl  
- **Delay**: Limit traffic by adding delay (seconds) between requests  
- **Output**: Save results to a JSON file

python webcrawler.py --web <website_url> --max-depth 2 --max-pages 30 --delay 1 --output custom.json


---

### 3. Include / Exclude Links

- **Include**: Crawl only links matching this pattern  
- **Exclude**: Skip links matching this pattern

python webcrawler.py --web <website_url> --include '(^|/)interested(/|$)' --exclude 'not_interested'


> - Example of interested links: `/interested/`  
> - Example of links to exclude: `?not_interested`

---

### 4. JavaScript-Rendered or Dynamically Loaded Pages

For websites that load content dynamically using JavaScript, enable rendering with a headless browser:

python webcrawler.py --web <website_url> --render --headless


> This uses Selenium with headless mode to render pages before crawling.

---

## Notes

- Make sure you have [Selenium](https://www.selenium.dev/) installed if you're using the `--render` option.  
- Use crawling responsibly and respect websites' `robots.txt` and terms of service.  

---

Feel free to contribute or open issues for improvements!

