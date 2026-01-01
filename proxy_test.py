from curl_cffi import requests
import json

def run_test(target_version="chrome124"):
    # This URL returns your JA3 and Akamai fingerprints as seen by the server
    url = "https://tls.browserleaks.com/json"
    
    # Matching the User-Agent to the impersonation target is crucial
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    
    print(f"--- Testing Fingerprint: {target_version} ---")
    try:
        # We test chrome124 as it is more modern than the 120 currently in your code
        response = requests.get(url, headers=headers, impersonate=target_version, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Success! Status Code: {response.status_code}")
            print(f"JA3 Hash: {data.get('ja3_hash')}")
            print(f"JA4 Fingerprint: {data.get('ja4')}")
            print(f"Akamai Fingerprint: {data.get('akamai_hash')}")
        else:
            print(f"❌ Failed! Status Code: {response.status_code}")
            print(response.text)
            
    except Exception as e:
        print(f"⚠️ Error: {e}")

if __name__ == "__main__":
    # Test both your current version and the recommended upgrade
    run_test("chrome120")
    print("\n" + "="*40 + "\n")
    run_test("chrome124")