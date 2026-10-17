import pandas as pd

cards = pd.read_csv("data/card.csv", sep="\t", dtype=str)
printings = pd.read_csv("data/card-printing.csv", sep="\t", dtype=str)

# drop the empty columns on the right
printings = printings.loc[:, ~printings.columns.str.startswith("Unnamed")]

print("cards:", cards.shape)
print("printings:", printings.shape)

# filter: all printings of one card
force = printings[printings["Card Name"] == "Abyssal Force"]
print(force[["Card ID", "Set ID", "Foiling"]])

# count distinct values
print(printings["Foiling"].value_counts())

# is Card ID unique? is Unique ID?
print("Card ID repeats:", printings["Card ID"].duplicated().sum())
print("Unique ID is unique:", printings["Unique ID"].is_unique)

# merge: add each card's name, colour and pitch to its printings
cards2 = cards[["Unique ID", "Name", "Color", "Pitch"]].rename(
    columns={"Unique ID": "Card Unique ID"})
merged = printings.merge(cards2, on="Card Unique ID", how="left")
print(merged[["Name", "Color", "Pitch", "Card ID", "Foiling"]].head())