import requests
import json
import random

# Fetch all countries from the API
url = "https://restcountries.com/v3.1/all?fields=name,capital,population,languages,currencies,flag,subregion,area,borders"
response = requests.get(url)
all_countries = response.json()


# Pick a random country
country = random.choice(all_countries)

# Extract data
name = country['name']['common']
capital = country.get('capital', [None])[0]
population = country.get('population', None)
languages = list(country.get('languages', {}).values())
currencies = [v['name'] for v in country.get('currencies', {}).values()]
subregion = country.get('subregion', '')
area = country.get('area', None)
borders = country.get('borders', [])

print(f"\nToday's country: {name}")
print("Answer the following questions:\n")

score = 0
total = 0

# Capital question
if capital:
    total += 1
    guess = input("What is the capital? ")
    if guess.lower() == capital.lower():
        print("Correct!")
        score += 1
    else:
        words = capital.split()
        word_lengths = ' + '.join(str(len(w)) for w in words)
        hint_text = f"{len(words)} words, lengths: {word_lengths}" if len(words) > 1 else f"{len(capital)} letters"
        print(f"Incorrect! Hint: The capital starts with '{capital[0]}' and has {hint_text}.")
        guess2 = input("Try again: ")
        if guess2.lower() == capital.lower():
            print("Correct!")
            score += 0.5
        else:
            print(f"Wrong! The answer was {capital}")

# Population question
if population:
    total += 1
    guess = input("\nWhat is the population? ")
    try:
        guess_number = int(guess)
        difference = abs(guess_number - population) / population
        if difference <= 0.20:
            print("Correct! (within 20%)")
            score += 1
        else:
            print(f"Wrong! The answer was {population:,}")
    except:
        print(f"Invalid number. The answer was {population:,}")

# Language question
if languages:
    total += 1
    guess = input("\nName one official language? ")
    if guess.lower() in [l.lower() for l in languages]:
        print(f"Correct! All official languages: {', '.join(languages)}")
        score += 1
    else:
        hint = languages[0]
        print(f"Incorrect! Hint: One language starts with '{hint[0]}' and has {len(hint)} letters.")
        guess2 = input("Try again: ")
        if guess2.lower() in [l.lower() for l in languages]:
            print(f"Correct! All official languages: {', '.join(languages)}")
            score += 0.5
        else:
            print(f"Wrong! All official languages: {', '.join(languages)}")

# Currency question
if currencies:
    total += 1
    guess = input(f"\nWhat is the currency? ")
    if any(guess.lower() in c.lower() or c.lower() in guess.lower() for c in currencies):
        print("Correct!")
        score += 1
    else:
        print(f"Wrong! Accepted answers: {', '.join(currencies)}")

# Fun fact at the end
print("\n--- Country Fact ---")
facts = []
if subregion:
    facts.append(f"{name} is located in {subregion}.")
if area:
    facts.append(f"It covers an area of {area:,.0f} km².")
if len(borders) == 0:
    facts.append(f"It has no land borders — it's an island nation or territory.")
elif len(borders) == 1:
    facts.append(f"It shares a border with just one country.")
else:
    facts.append(f"It shares borders with {len(borders)} countries.")

if facts:
    for fact in facts:
        print(f"• {fact}")

print(f"\nYou scored {score} out of {total}")