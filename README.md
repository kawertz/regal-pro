# 🎬 Regal Pro (RC 1.3)

The current version of app is deployed at [Streamlit Community](https://regal-pro.streamlit.app/). Use this if you simply want use the app.

A compiled binary is available on the [releases page](https://github.com/riyazusman/regal-pro/releases/). Use this if you want a local executable, but don't want to install python or any libraries.

If you want to build or run from source, instructions are at the end of this document.

## 🚀 Quick Start
1. Search for your theater in the **Sidebar** using Zip, Theater Name, Street/City or 4 digit Theater Code.
2. Select a **Date**.
3. Use the **Theater Explorer** to see what's playing.
	- Filter by Screen Type, Auditorium, Time Windows, Rating and Additional Attributes
	- Sort by Movie Title, Showtime or Auditorium
	- Group results by Movie, Auditorium or Full Schedule
4. Use the **Smart Scheduler** to build back-to-back itineraries (For a single theater and day).
	- Select 2 or more movies to build a Schedule
	- Select Formats, Specify Earliest Start and Latest End, Minimum Buffer between movies, Maximum Gap between movies and Long Break preference.
	- Optionally enforce Regal Unlimited 91 min gap between shows Rule.
	- Optionally enable a Fudge Factor to allow 5 minute overlap between showtimes. This will be used only if scheduler is not otherwise able to create an itinerary.
	- View Top 3 iteneraries ranked by priority, most movies and least gap. 
	- Download ICS to import a schedule to your calendar.

## 🗓️ Scheduling Logic
The app uses a **Weighted Hybrid Algorithm**:
- **Priority:** Movies are weighted based on the order you select them in the dropdown.
- **Constraints:** The engine strictly follows your Buffer, Max Gap, and Format preferences.
- **Results:** - **Top 2:** Best paths containing your #1 and #2 priority movies.
    - **Max Count:** The path that fits the most movies possible, regardless of priority (provided it meets or beats the count of the priority paths).
	
## 🛠️ Technical Notes
- **Data Source:** Fetched live from Regal API.
- **Time Zone Sync** App sync timezone based on selected theater. User can manually set UTC offset. This will be used for past shows filter and scheduling.
- **Debug Mode** Advanced Settings allows you to view raw API data. This is critical for identifying why a specific theater might be missing showtimes or formatting data unexpectedly.
- **Force Refresh:** If Regal blocks the request, manually initiate data.

## 🖨️ Printing

Enable **Print View** in the sidebar to remove UI elements for a clean paper schedule.


## Run from Source Instructions
### Install Python
1. Download: Go to [python.org/downloads](https://www.python.org/downloads/).
2. Run Installer: Open the downloaded file.
   - CRITICAL STEP: On the first screen of the installer, check the box that says "Add Python to PATH".
3. Install: Click Install Now.

### Download the Project from GitHub
1. Click the green "<> Code" button on top of this page.
2. Select "Download ZIP".
3. Extract: Open your "Downloads" folder, right-click the ZIP file, and select Extract All. Navigate to the extracted folder.
4. Run the Application
	- If you are on Windows, open run_regal.bat.
 	- If you are on Mac/Linux open run_regal.sh. 
5. The executable will check and install required python libraries. Wait for the text to stop scrolling. This usually takes about 30–60 seconds. Installing the libraries are required only for the first run.

## Access the App
1. Your web browser should automatically open to a new tab at http://localhost:8501.
2. The Regal Pro interface will appear.
3. To stop the app: Go back to the Terminal and press Ctrl + C on your keyboard.
