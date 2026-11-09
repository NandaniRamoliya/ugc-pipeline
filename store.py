import gspread
from gspread.utils import rowcol_to_a1

from config import GOOGLE_SA_INFO, SHEET_ID

CONTENT_HEADERS = [
    "id", "created_at", "status", "product_id", "product_name", "angle", "hook",
    "shots_json", "caption", "hashtags", "folder_id", "video_url", "cover_url",
    "scheduled_at", "container_id", "ig_media_id", "permalink",
    "views", "reach", "likes", "comments", "saves", "shares", "error",
]
PRODUCT_HEADERS = ["product_id", "name", "brand", "category", "key_benefits", "notes", "status"]
STATE_HEADERS = ["key", "value"]

_book = None
_tables = {}


def book():
    global _book
    if _book is None:
        _book = gspread.service_account_from_dict(GOOGLE_SA_INFO).open_by_key(SHEET_ID)
    return _book


class Table:
    def __init__(self, title, headers):
        try:
            self.ws = book().worksheet(title)
        except gspread.WorksheetNotFound:
            self.ws = book().add_worksheet(title=title, rows=1000, cols=max(len(headers), 10))
        current = self.ws.row_values(1)
        missing = [h for h in headers if h not in current]
        if missing:
            current = current + missing
            if len(current) > self.ws.col_count:
                self.ws.add_cols(len(current) - self.ws.col_count)
            self.ws.batch_update([{"range": "A1", "values": [current]}])
        self.headers = current

    def all(self):
        out = []
        for i, row in enumerate(self.ws.get_all_values()[1:], start=2):
            if not any(c.strip() for c in row):
                continue
            row = row + [""] * (len(self.headers) - len(row))
            rec = dict(zip(self.headers, row))
            rec["_row"] = i
            out.append(rec)
        return out

    def update(self, rec, **fields):
        data = [{"range": rowcol_to_a1(rec["_row"], self.headers.index(k) + 1), "values": [[str(v)]]}
                for k, v in fields.items()]
        self.ws.batch_update(data, value_input_option="RAW")
        rec.update({k: str(v) for k, v in fields.items()})

    def append(self, rec):
        self.ws.append_row([str(rec.get(h, "")) for h in self.headers],
                           value_input_option="RAW", table_range="A1")


def table(title, headers):
    if title not in _tables:
        _tables[title] = Table(title, headers)
    return _tables[title]


def content():
    return table("Content", CONTENT_HEADERS)


def products():
    return table("Products", PRODUCT_HEADERS)


def state_get(key, default=""):
    for r in table("State", STATE_HEADERS).all():
        if r["key"] == key:
            return r["value"]
    return default


def state_set(key, value):
    t = table("State", STATE_HEADERS)
    for r in t.all():
        if r["key"] == key:
            t.update(r, value=value)
            return
    t.append({"key": key, "value": value})

