import requests
import json
from selenium import webdriver # launch and control browser  
from selenium.webdriver.common.by import By # to locate element in page we use by
from selenium.webdriver.support.ui import WebDriverWait # hepls ot wait untill a condition happens on a page
from selenium.webdriver.support import expected_conditions as EC # provide condition to wait for 
from selenium.webdriver.chrome.service import Service # config. chrome service
from selenium.webdriver.chrome.options import Options # helps to setup the chrome browser options
from webdriver_manager.chrome import ChromeDriverManager # download and manage correct version of chrome driver
import time
import random

from dotenv import load_dotenv
from langchain_groq import ChatGroq
import os
import json

load_dotenv()
key = os.getenv("GROQ_API_KEY")
model = ChatGroq(model="llama-3.3-70b-versatile", api_key=key)


# first try with rapid api 
def check_pnr_rapidapi(pnr_number):
    print("\n 1. first try with rapid api. . .")
    
    url = f"https://irctc-indian-railway-pnr-status.p.rapidapi.com/getPNRStatus/{pnr_number}"
    
    headers = {
        "x-rapidapi-key": "bed019e806mshd2f80db29f2db8ep1c2a63jsne6c04ab81f0c",
        "x-rapidapi-host": "irctc-indian-railway-pnr-status.p.rapidapi.com"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Check if response contains valid data
        if data and "error" not in str(data).lower():
            print("rapid api success")
            return data
        else:
            print("RapidAPI gives error or invalid data")
            return None
            
    except Exception as e:
        print(f" rapid api fail: {str(e)}")
        return None


# not 1 then try the 2 selenium automation
def create_stealth_driver():

    """this fn makes Selenium Chrome browser that is:
        - Headless (runs in background)
        - Harder for websites to detect
        - Faster and optimized
        - Looks like a real human browser"""
    
    chrome_options = Options() # adding settings for chrome
    
    
    chrome_options.add_argument('--headless=new') # run browser without opening a window
    
    # all the below, make the browser harder to detect by websites.
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--disable-infobars')
    chrome_options.add_argument('--disable-extensions')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--disable-software-rasterizer')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--start-maximized')
    
    # normal user using chrome
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36') 
    
    
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # remove faltu ka pop-ups
    prefs = {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
        "profile.default_content_setting_values.notifications": 2
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    # download chrome driver and create chrome browser
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # hide webdriver property
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {
        "userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
    })
    
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    
    return driver




def parse_ticket_data(page_text, pnr_number):
    """
    Parse the page text to extract structured ticket information
    """
    ticket_data = {
        'pnr': pnr_number,
        'train_number': None,
        'train_name': None,
        'from_station': None,
        'to_station': None,
        'date_of_journey': None,
        'class': None,
        'chart_status': None,
        'passengers': []
    }
    
    lines = page_text.split('\n')
    
    # Extract train info
    for i, line in enumerate(lines):
        if ' - ' in line and 'EXP' in line.upper() or 'SF' in line.upper():
            parts = line.split(' - ')
            if len(parts) >= 2:
                ticket_data['train_number'] = parts[0].strip()
                ticket_data['train_name'] = parts[1].strip()
                break
    
    # Extract station info
    for i, line in enumerate(lines):
        if 'Junction' in line or 'BSB' in line:
            parts = line.split(' - ')
            if len(parts) == 2:
                ticket_data['from_station'] = parts[0].strip()
        
        if 'New Delhi' in line or 'NDLS' in line:
            parts = line.split(' - ')
            if len(parts) == 2:
                ticket_data['to_station'] = parts[0].strip()
    
    # Extract date and class
    for line in lines:
        if '|' in line and ('E' in line or 'GN' in line):
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 2:
                ticket_data['date_of_journey'] = parts[0].strip()
                ticket_data['class'] = parts[1].strip()
    
    # Extract chart status
    if 'Chart not prepared' in page_text:
        ticket_data['chart_status'] = 'Chart not prepared'
    elif 'Chart prepared' in page_text:
        ticket_data['chart_status'] = 'Chart prepared'
    
    # Extract passenger information
    for i, line in enumerate(lines):
        if line.strip().isdigit() and int(line.strip()) <= 10:
            # Look ahead for status info
            if i + 1 < len(lines):
                current_status = lines[i + 1].strip()
                booking_status = lines[i + 2].strip() if i + 2 < len(lines) else ''
                coach = lines[i + 3].strip() if i + 3 < len(lines) else ''
                
                if 'CNF' in current_status or 'WL' in current_status or 'RAC' in current_status:
                    passenger = {
                        'serial_number': int(line.strip()),
                        'current_status': current_status,
                        'booking_status': booking_status if booking_status and not booking_status.isdigit() else current_status,
                        'coach': coach if len(coach) <= 3 else ''
                    }
                    ticket_data['passengers'].append(passenger)
    
    return ticket_data


def check_pnr_automation(pnr_number):
    print("\n 2: trying Selenium automation ...")
    
    driver = create_stealth_driver() # create hidden browser 
    
    try:
        # go to website
        print("Connecting to ConfirmTKT website...")
        driver.get('https://www.confirmtkt.com/pnr-status') # opens the website
        
        time.sleep(random.uniform(2, 4)) # wait for 2-3 sec
        
        wait = WebDriverWait(driver, 20) # selenium wait for 20 sec
        
        # find PNR input field
        print(" find PNR input field...")
        pnr_input = None
        selectors = [
            (By.NAME, 'pnr'),
            (By.ID, 'pnrNumber'),
            (By.XPATH, "//input[@placeholder='Enter PNR Number']"),
            (By.XPATH, "//input[contains(@placeholder, 'PNR')]"),
            (By.CSS_SELECTOR, "input[type='text']")
        ]
        
        for by, selector in selectors:
            try:
                pnr_input = wait.until(EC.element_to_be_clickable((by, selector)))
                print(" Found PNR input field")
                break
            except:
                continue
        
        if pnr_input is None:
            raise Exception("Could not find PNR input field")
        
        # Human-like typing
        print(" entering PNR number...")
        pnr_input.click()
        time.sleep(random.uniform(0.3, 0.7))
        pnr_input.clear()
        
        # adding small delay to look like human
        for char in pnr_number:
            pnr_input.send_keys(char)
            time.sleep(random.uniform(0.05, 0.15))
        
        print(f"Entered PNR: {pnr_number}")
        
        time.sleep(random.uniform(0.5, 1.5))
        
        # Find and click submit button
        print(" Finding submit button...")
        submit_button = None
        button_selectors = [
            (By.XPATH, "//button[@type='submit']"),
            (By.XPATH, "//button[contains(text(), 'Check Status')]"),
            (By.XPATH, "//button[contains(@class, 'submit')]"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.TAG_NAME, "button")
        ]
        
        for by, selector in button_selectors:
            try:
                submit_button = wait.until(EC.element_to_be_clickable((by, selector)))
                print("Found submit button")
                break
            except:
                continue
        
        if submit_button is None:
            raise Exception("Could not find submit button")
        
        driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
        time.sleep(random.uniform(0.3, 0.7))
        
        submit_button.click()
        print(" Submitted PNR query")
        print(" Waiting for results...\n")
        
        time.sleep(random.uniform(8, 10))
        
        # Get page content
        page_text = driver.find_element(By.TAG_NAME, 'body').text
        page_html = driver.page_source
        
        # Check for errors
        if "Something went wrong" in page_text or "Sorry!" in page_text:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(3)
            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)
            page_text = driver.find_element(By.TAG_NAME, 'body').text
        
        # Save HTML for debugging
        try:
            with open('pnr_result.html', 'w', encoding='utf-8') as f:
                f.write(page_html)
        except:
            pass
        
        # Parse the ticket data
        ticket_details = parse_ticket_data(page_text, pnr_number)
        
        if ticket_details['chart_status']:
            print(" Success")
        
        return ticket_details
        
    except Exception as e:
        print(f"\n Automation Error: {str(e)}")
        try:
            driver.save_screenshot('error_screenshot.png')
            print("Screenshot saved as error_screenshot.png")
        except:
            pass
        return None
        
    finally:
        driver.quit()
        print("Browser closed")


# Main Combined Function
def check_pnr_combined(pnr_number):
    
    print(f" Checking PNR: {pnr_number}")
    print("-"*70)
    
    # Validate PNR
    if len(str(pnr_number)) != 10 or not str(pnr_number).isdigit():
        print("Invalid PNR! Must be 10 digits.")
        return None
    
    # Step 1: Try RapidAPI
    print("\nTrying rapid API ")
    print("-"*70)
    
    api_result = check_pnr_rapidapi(pnr_number)
    if api_result:
        return api_result
    
    # Step 2: Fallback to Automation
    print("\nAPI failed. trying automation")
    print("-"*70)
    
    automation_result = check_pnr_automation(str(pnr_number))
    if automation_result:
        return automation_result
    
    # Both methods failed
    print("\n" + "-"*70)
    print("  FAILED")
    print("-"*70)
    print("Possible reasons:")
    print("  1. Invalid PNR number")
    print("  2. API rate limit exceeded")
    print("  3. Website is down or blocking requests")
    print("  4. Network connectivity issues")
    print("\n Please try again in a few minutes or verify your PNR number")
    print("="*70)
    
    return None





def generate_pnr_summary(json_data):
    
    
    if not json_data:
        return "❌ No PNR data available to summarize."
    
    # Convert JSON to string for the LLM
    json_str = json.dumps(json_data, indent=2)
    
    # Create prompt for the LLM
    prompt = f"""You are an Indian Railway PNR assistant.

Output must be extremely short, clear and spoken-friendly because it will be sent to a text-to-speech engine.

Rules:
- DO NOT repeat the PNR number.
- Give all ticket details together in one short paragraph.
- Include: train name and number,name of passagers, class, from–to stations, date, chart status, passenger booking status, and a very short probability of getting confirmed. only if ticket is not confirmed(like 'high', 'medium', or 'low').
- Keep sentences tiny and natural.
- End with a friendly greeting like: "Thank you and have a safe journey."
- note : do not make the answer if there is no information

PNR Data:
{json_str}

Summary:"""
    
    try:
        # Get response from LLM
        response = model.invoke(prompt)
        summary = response.content.strip()
        return summary
        
    except Exception as e:
        return f"⚠️ Error generating summary: {str(e)}\n\nRaw data available - check JSON output."





if __name__ == "__main__":
    # Enter your PNR number here
    PNR_NUMBER = "2608290686"
    
    result = check_pnr_combined(PNR_NUMBER)
    llm_result = generate_pnr_summary(result)
    
    print(llm_result)


