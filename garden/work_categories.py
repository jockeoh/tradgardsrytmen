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


def suggested_work_category(title):
    """Return a category only when the task title gives a strong signal."""
    text = (title or "").strip().casefold()
    if not text:
        return None
    if text.startswith(("kontrollera", "inspektera", "sommarinspektera", "följ ", "inventera", "övervaka")):
        return "Kontrollera"
    if text.startswith("bedöm"):
        return "Gödsla" if any(word in text for word in ("göd", "näring")) else "Kontrollera"
    if any(word in text for word in ("göd", "näring")):
        return "Gödsla"
    if any(word in text for word in ("jord", "ogräs", "marktäck", "luckra")):
        return "Jord och ogräs"
    if text.startswith(("vattna", "bevattna")) or " ge vatten" in f" {text}":
        return "Vattna"
    if any(word in text for word in ("beskär", "gallra", "bind upp", "klipp")):
        return "Beskära och binda upp"
    if any(word in text for word in ("skörda", "plocka")):
        return "Skörda"
    return None


def normalize_work_category(value, title="", instructions=""):
    """Map legacy and free-form labels to the fixed work categories."""
    if value in WORK_CATEGORIES:
        return value
    suggested = suggested_work_category(title)
    if suggested:
        return suggested
    text = f"{value or ''} {instructions or ''}".casefold()
    mappings = (
        ("Kontrollera", ("kontroll", "inspek", "inventera", "övervaka", "håll utkik", "bedöm", "följ upp", "växtskydd", "sjuk", "skadedjur")),
        ("Vattna", ("vatt", "bevatt")),
        ("Gödsla", ("göd", "näring", "kompostte", "npk")),
        ("Jord och ogräs", ("jord", "ogräs", "luckra", "täck", "mulch", "kompost")),
        ("Beskära och binda upp", ("beskär", "gallra", "bind", "stötta", "klipp", "skott")),
        ("Skörda", ("skörd", "plocka", "frukt", "bär")),
    )
    for category, needles in mappings:
        if any(needle in text for needle in needles):
            return category
    return "Övrigt"
