# 🎬 Regal Reactive Pro (RC 1.2)

## 🚀 Quick Start
1. Search for your theater in the **Sidebar** using Zip, Theater Name, Street/City or 4 digit Theater Code.
2. Select a **Date**.
3. Use the **Theater Explorer** to see what's playing.
	- Filter by Screen Type, Auditorium, Time Windows, Rating and Additional Attributes
	- Sort by Movie Title, Showtime or Auditorium
	- Group results by Movie, Auditorium or Full Schedule
4. Use the **Smart Scheduler** to build back-to-back itineraries.
	- Select 2 or more movies to build a Schedule
	- Select Formats, Specify Earliest Start and Latest End, Minimum Buffer between movies, Maximum Gap between movies and Long Break preference.
	- Enforce Regal Unlimited 91 Min Rule.
	- Enable Fudge Factor to allow 5 minuite overlap between showtimes if scheduler is not otherwise able to create an itinerary.
	- Download ICS to import a schedule to your calendar.	

## 🗓️ Scheduling Logic
The app uses a **Weighted Hybrid Algorithm**:
- **Priority:** Movies are weighted based on the order you select them in the dropdown.
- **Constraints:** The engine strictly follows your Buffer, Max Gap, and Format preferences.
- **Results:** - **Top 2:** Best paths containing your #1 and #2 priority movies.
    - **Max Count:** The path that fits the most movies possible, regardless of priority (provided it meets or beats the count of the priority paths).
	
## 🛠️ Technical Notes
- **Data Source:** Fetched live from Regal API.
- **Time Zone Sync** App sync timezone based on selected theater. User can manually set UTC offset.
- **Debug Mode** Advanced Settings allows you to view raw API data. This is critical for identifying why a specific theater might be missing showtimes or formatting data unexpectedly.
- **Force Refresh:** If Regal blocks the request, manually initiate data.

## 🖨️ Printing
Enable **Print View** in the sidebar to remove UI elements for a clean paper schedule.