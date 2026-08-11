WORK_CATEGORIES = (
    "Vattna",
    "Beskära och binda upp",
    "Kontrollera",
    "Gödsla",
    "Jord och ogräs",
    "Skörda",
    "Övrigt",
)

WORK_CATEGORY_CHOICES = [(category, category) for category in WORK_CATEGORIES]


def normalize_work_category(value, fallback_text=""):
    """Map legacy and free-form labels to the fixed work categories."""
    if value in WORK_CATEGORIES:
        return value
    text = f"{value or ''} {fallback_text or ''}".casefold()
    mappings = (
        ("Vattna", ("vatt", "bevatt")),
        ("Beskära och binda upp", ("beskär", "gallra", "bind", "stötta", "klipp", "skott")),
        ("Kontrollera", ("kontroll", "inspek", "övervaka", "håll utkik", "bedöm", "följ upp", "sjuk", "skadedjur")),
        ("Gödsla", ("göd", "näring", "kompostte", "npk")),
        ("Jord och ogräs", ("jord", "ogräs", "luckra", "täck", "mulch", "kompost")),
        ("Skörda", ("skörd", "plocka", "frukt", "bär")),
    )
    for category, needles in mappings:
        if any(needle in text for needle in needles):
            return category
    return "Övrigt"
