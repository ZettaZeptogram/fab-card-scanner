import sqlite3
import pandas as pd

DB = "collection.db"

SCHEMA = """
         CREATE TABLE IF NOT EXISTS printings (
                                                  printing_id    TEXT PRIMARY KEY,
                                                  name           TEXT NOT NULL,
                                                  color          TEXT,
                                                  pitch          INTEGER,
                                                  set_code       TEXT NOT NULL,
                                                  set_no         INTEGER NOT NULL,
                                                  card_id        TEXT NOT NULL,
                                                  edition        TEXT,
                                                  rarity         TEXT,
                                                  foiling        TEXT,
                                                  art_variations TEXT,
                                                  finish         TEXT NOT NULL,
                                                  image_url      TEXT
         );
         CREATE INDEX IF NOT EXISTS idx_printings_name ON printings(name);
         CREATE INDEX IF NOT EXISTS idx_printings_set ON printings(set_code, set_no);

         CREATE TABLE IF NOT EXISTS collection (
                                                   id            INTEGER PRIMARY KEY,
                                                   printing_id   TEXT NOT NULL REFERENCES printings(printing_id),
                                                   quantity      INTEGER NOT NULL CHECK (quantity >= 1),
                                                   price_pence   INTEGER CHECK (price_pence IS NULL OR price_pence >= 0),
                                                   purchase_date TEXT,
                                                   notes         TEXT
         ); \
         """

COLS = ["printing_id", "name", "color", "pitch", "set_code", "set_no", "card_id",
        "edition", "rarity", "foiling", "art_variations", "finish", "image_url"]


def load_printings():
    cards = pd.read_csv("data/card.csv", sep="\t", dtype=str)
    prints = pd.read_csv("data/card-printing.csv", sep="\t", dtype=str)
    prints = prints.loc[:, ~prints.columns.str.startswith("Unnamed")]

    cards = cards[["Unique ID", "Name", "Color", "Pitch"]].rename(
        columns={"Unique ID": "Card Unique ID"})
    df = prints.merge(cards, on="Card Unique ID", how="left")

    # set number = the card ID with the set code removed from the front
    df["set_no"] = df.apply(lambda r: int(r["Card ID"][len(r["Set ID"]):]), axis=1)
    df["pitch"] = pd.to_numeric(df["Pitch"]).astype("Int64")

    # a suggested finish label from foiling and art variation
    base = {"S": "NF", "R": "RF", "C": "CF"}
    ea = df["Art Variations"].fillna("").str.contains("EA")
    df["finish"] = [base.get(f, "Other") + (" EA" if e and f in base else "")
                    for f, e in zip(df["Foiling"], ea)]

    df = df.rename(columns={
        "Unique ID": "printing_id", "Name": "name", "Color": "color",
        "Set ID": "set_code", "Card ID": "card_id", "Edition": "edition",
        "Rarity": "rarity", "Foiling": "foiling",
        "Art Variations": "art_variations", "Image URL": "image_url"})
    return df[COLS]


def refill_catalogue(conn, df):
    # upsert: add new printings, update changed ones, never delete rows
    # your collection points at (a delete would break those links)
    updates = ", ".join(f"{c}=excluded.{c}" for c in COLS if c != "printing_id")
    sql = (f"INSERT INTO printings ({', '.join(COLS)}) "
           f"VALUES ({', '.join('?' * len(COLS))}) "
           f"ON CONFLICT(printing_id) DO UPDATE SET {updates}")
    rows = df.astype(object).where(df.notna(), None).values.tolist()
    with conn:
        conn.executemany(sql, rows)


if __name__ == "__main__":
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    refill_catalogue(conn, load_printings())
    n = conn.execute("SELECT COUNT(*) FROM printings").fetchone()[0]
    print("printings in catalogue:", n)
    conn.execute("SELECT COUNT(*) FROM printings")
    conn.close()