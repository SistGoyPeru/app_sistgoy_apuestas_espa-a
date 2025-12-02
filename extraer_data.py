import requests
from bs4 import BeautifulSoup
import polars as pl
from datetime import datetime

class CalendarExtractor:
    def __init__(self, url):
        self.url = url
        self.data = []

    def fetch_and_parse(self):
        print(f"Fetching {self.url}...")
        response = requests.get(self.url)
        if response.status_code != 200:
            print(f"Failed to fetch URL: {response.status_code}")
            return

        soup = BeautifulSoup(response.content, 'html.parser')
        
        container = soup.find('div', class_='module-gameplan')
        if not container:
            print("Could not find module-gameplan container")
            return

        wrapper = container.find('div', recursive=False)
        if not wrapper:
            print("Could not find wrapper div")
            return

        current_round = None
        
        for child in wrapper.find_all(recursive=False):
            classes = child.get('class', [])
            
            if 'round-head' in classes:
                current_round = child.get_text(strip=True)
                
            elif 'match' in classes:
                self._process_match(child, current_round)

    def _process_match(self, child, current_round):
        datetime_str = child.get('data-datetime')
        date_val = None
        time_val = None
        
        if datetime_str:
            try:
                dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                date_val = dt.strftime('%Y-%m-%d')
                time_val = dt.strftime('%H:%M')
            except ValueError:
                pass
        
        if not time_val:
            time_div = child.find('div', class_='match-time')
            if time_div:
                time_val = time_div.get_text(strip=True)

        home_div = child.find('div', class_='team-name-home')
        away_div = child.find('div', class_='team-name-away')
        
        home_team = home_div.get_text(strip=True) if home_div else "Unknown"
        away_team = away_div.get_text(strip=True) if away_div else "Unknown"
        
        result_div = child.find('div', class_='match-result')
        score_text = result_div.get_text(strip=True) if result_div else None
        
        home_goals = None
        away_goals = None

        if score_text and ":" in score_text and score_text != "-:-":
            try:
                parts = score_text.split(":")
                if len(parts) == 2:
                    home_goals = int(parts[0])
                    away_goals = int(parts[1])
            except ValueError:
                pass

        self.data.append({
            "Jornada": current_round,
            "Fecha": date_val,
            "Hora": time_val,
            "Local": home_team,
            "Visita": away_team,
            "GA": home_goals,
            "GC": away_goals
        })

    def get_dataframe(self):
        if not self.data:
            return pl.DataFrame()
        return pl.DataFrame(self.data)

    def save_to_csv(self, output_file="calendario_liga.csv"):
        df = self.get_dataframe()
        if df.is_empty():
            print("No match data found.")
            return

import requests
from bs4 import BeautifulSoup
import polars as pl
from datetime import datetime

class CalendarExtractor:
    def __init__(self, url):
        self.url = url
        self.data = []

    def fetch_and_parse(self):
        print(f"Fetching {self.url}...")
        response = requests.get(self.url)
        if response.status_code != 200:
            print(f"Failed to fetch URL: {response.status_code}")
            return

        soup = BeautifulSoup(response.content, 'html.parser')
        
        container = soup.find('div', class_='module-gameplan')
        if not container:
            print("Could not find module-gameplan container")
            return

        wrapper = container.find('div', recursive=False)
        if not wrapper:
            print("Could not find wrapper div")
            return

        current_round = None
        
        for child in wrapper.find_all(recursive=False):
            classes = child.get('class', [])
            
            if 'round-head' in classes:
                current_round = child.get_text(strip=True)
                
            elif 'match' in classes:
                self._process_match(child, current_round)

    def _process_match(self, child, current_round):
        datetime_str = child.get('data-datetime')
        date_val = None
        time_val = None
        
        if datetime_str:
            try:
                dt = datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
                date_val = dt.strftime('%Y-%m-%d')
                time_val = dt.strftime('%H:%M')
            except ValueError:
                pass
        
        if not time_val:
            time_div = child.find('div', class_='match-time')
            if time_div:
                time_val = time_div.get_text(strip=True)

        home_div = child.find('div', class_='team-name-home')
        away_div = child.find('div', class_='team-name-away')
        
        home_team = home_div.get_text(strip=True) if home_div else "Unknown"
        away_team = away_div.get_text(strip=True) if away_div else "Unknown"
        
        result_div = child.find('div', class_='match-result')
        score_text = result_div.get_text(strip=True) if result_div else None
        
        home_goals = None
        away_goals = None

        if score_text and ":" in score_text and score_text != "-:-":
            try:
                parts = score_text.split(":")
                if len(parts) == 2:
                    home_goals = int(parts[0])
                    away_goals = int(parts[1])
            except ValueError:
                pass

        self.data.append({
            "Jornada": current_round,
            "Fecha": date_val,
            "Hora": time_val,
            "Local": home_team,
            "Visita": away_team,
            "GA": home_goals,
            "GC": away_goals
        })

    def get_dataframe(self):
        if not self.data:
            return pl.DataFrame()
        return pl.DataFrame(self.data)

    def save_to_csv(self, output_file="calendario_liga.csv"):
        df = self.get_dataframe()
        if df.is_empty():
            print("No match data found.")
            return

        print(f"Extracted {len(df)} matches.")
        print(df.head())
        
        df.write_csv(output_file)
        print(f"Saved to {output_file}")

    def run(self):
        self.fetch_and_parse()
        self.save_to_csv()

if __name__ == "__main__":
    url = "https://www.livefutbol.com/competition/co97/espana-primera-division/all-matches/"
    extractor = CalendarExtractor(url)
    extractor.run()