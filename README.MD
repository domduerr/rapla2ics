# 📅 Calendar ICS Server

This project fetches a [rapla](https://github.com/rapla/rapla) HTML schedule, parses it, and serves it as an `.ics` calendar file that can be imported into applications like Thunderbird, Outlook, or any other calendar app supporting the iCalendar format.

It includes caching for performance and reliability, skips "Abwesenheit" (absence) events, and is fully Dockerized for easy deployment.

## 🔧 Usage
1. Clone the repository:
```bash
git clone https://github.com/domduerr/rapla2ics.git
cd calendar-ics-server
```
2. Configure environment:
    - Rename `.env.example` to `.env`
    - Fill in the required environment variables in the `.env` file
3. Build and run the server:
```bash
docker-compose up --build -d
```
4. Access your calendar:
```
    http://localhost:8080/calendar.ics
```