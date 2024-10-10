import os
import json
import requests
import pandas as pd
import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed
from fake_useragent import UserAgent
from zipfile import ZipFile

# Initialize UserAgent safely
try:
    ua = UserAgent()
except Exception as e:
    st.warning(f"Failed to initialize UserAgent: {e}")
    ua = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
    }

class URLChecker:
    def __init__(self, timeout=5, max_workers=5):
        self.timeout = timeout
        self.max_workers = max_workers

    def check_url(self, url):
        headers = {
            "User-Agent": ua.random if isinstance(ua, UserAgent) else ua["User-Agent"],
            "Referer": "https://www.google.com/",
        }

        session = requests.Session()
        try:
            response = session.get(url, headers=headers, timeout=self.timeout, allow_redirects=False)
            if response.status_code == 200:
                return "Working"
            elif 300 <= response.status_code < 400:
                return f"Redirect - Status Code: {response.status_code}"
            else:
                return f"Not Working - Status Code: {response.status_code}"
        except requests.exceptions.Timeout:
            return "Timeout"
        except requests.exceptions.RequestException as e:
            return f"Failed - {str(e)}"

    def process_urls(self, url_list):
        statuses = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self.check_url, url): url for url in url_list if url}
            for i, future in enumerate(as_completed(futures)):
                try:
                    status = future.result()
                except Exception as e:
                    status = f"Failed - {str(e)}"
                statuses.append(status)

                # Print progress in batches of 10 or at the end
                if (i + 1) % 10 == 0 or i == len(url_list) - 1:
                    st.write(f"Processed {i + 1} out of {len(url_list)} URLs")
        return statuses

class JSONReader:
    def __init__(self, json_file):
        self.json_file = json_file

    def read_urls(self):
        image_urls = []
        image_models = []
        attachment_urls = []
        attachment_models = []

        with open(self.json_file, "r", encoding='utf-8') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as e:
                st.error(f"Error reading JSON file: {e}")
                return [], [], [], []

        for json_model in data:
            model = json_model.get("general", {}).get("model")
            images = json_model.get("images", [])
            for image in images:
                url = image.get("src")
                if url:
                    image_urls.append(url)
                    image_models.append(model)

            attachments = json_model.get("attachments", [])
            for attachment in attachments:
                url = attachment.get("attachmentLocation")
                if url:
                    attachment_urls.append(url)
                    attachment_models.append(model)

        return image_models, image_urls, attachment_models, attachment_urls

class ExcelSaver:
    def __init__(self, output_file):
        self.output_file = output_file

    def save_to_excel(self, image_models, image_urls, image_statuses, attachment_models, attachment_urls, attachment_statuses):
        df_images = pd.DataFrame({"Model_name": image_models, "URL": image_urls, "Status": image_statuses})
        df_attachments = pd.DataFrame({"Model_name": attachment_models, "URL": attachment_urls, "Status": attachment_statuses})

        with pd.ExcelWriter(self.output_file) as writer:
            df_images.to_excel(writer, sheet_name="image_status", index=False)
            df_attachments.to_excel(writer, sheet_name="pdf_status", index=False)

        st.success(f"Results saved to {self.output_file}")

# Streamlit app configuration
st.title("URLs Checker")
st.write("Upload multiple JSON files to process URLs and check their status.")

# File uploader for multiple JSON files
uploaded_files = st.file_uploader("Choose JSON files", type=["json"], accept_multiple_files=True)

if uploaded_files:
    json_files = []
    for uploaded_file in uploaded_files:
        # Save the uploaded files to a temporary directory
        json_file_path = os.path.join("temp", uploaded_file.name)
        os.makedirs("temp", exist_ok=True)
        with open(json_file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        json_files.append(json_file_path)

    if not json_files:
        st.warning("No JSON files uploaded.")
    else:
        st.write(f"Found {len(json_files)} JSON files to process.")

        url_checker = URLChecker(max_workers=5)  # Fixed number of workers

        # Process URLs when button is clicked
        if st.button("Run URL Check"):
            results = []

            for json_file in json_files:
                st.write(f"<h3>Processing {os.path.basename(json_file)}</h3>", unsafe_allow_html=True)
                json_reader = JSONReader(json_file)
                image_models, image_urls, attachment_models, attachment_urls = json_reader.read_urls()

                if not image_urls and not attachment_urls:
                    st.warning(f"No URLs found in {os.path.basename(json_file)}.")
                    continue

                # Process image URLs
                st.write("<h4>Checking image URLs...</h4>", unsafe_allow_html=True)
                image_statuses = url_checker.process_urls(image_urls)

                # Process attachment URLs
                st.write("<h4>Checking attachment URLs...</h4>", unsafe_allow_html=True)
                attachment_statuses = url_checker.process_urls(attachment_urls)

                # Save results to an in-memory Excel file
                output_file = os.path.splitext(os.path.basename(json_file))[0] + "_results.xlsx"
                excel_saver = ExcelSaver(output_file)
                excel_saver.save_to_excel(image_models, image_urls, image_statuses, attachment_models, attachment_urls, attachment_statuses)

                results.append(output_file)

            # Provide a download link for all results
            if results:
                with ZipFile("all_results.zip", "w") as zipf:
                    for result_file in results:
                        zipf.write(result_file)

                with open("all_results.zip", "rb") as file:
                    st.download_button(label="Download All Results", data=file, file_name="all_results.zip", mime="application/zip")
