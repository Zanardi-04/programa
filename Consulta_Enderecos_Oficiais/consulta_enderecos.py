# -*- coding: utf-8 -*-
"""Consulta local de endereços, áreas e oficiais. Uso offline."""
import csv, json, os, re, sys, unicodedata, difflib, tkinter as tk, shutil
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import datetime

APP_TITLE = "Consulta de Endereços e Oficiais"
BASE_DIR = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
STREET_FILE = os.path.join(BASE_DIR, "lista_ruas_original.txt")
OFFICIALS_FILE = os.path.join(BASE_DIR, "oficiais.json")
ADJUST_FILE = os.path.join(BASE_DIR, "ajustes_locais.json")
AREAS_FILE = os.path.join(BASE_DIR, "areas.json")
HISTORY_FILE = os.path.join(BASE_DIR, "consultas_realizadas.csv")


def norm(s):
    s = unicodedata.normalize("NFD", str(s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.replace("º", " ").replace("°", " ")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def canonical_street(s):
    """Normaliza nomes de vias, títulos antes/depois do nome e abreviações."""
    x = norm(s)
    # Corrige tipo de via colado ao complemento: "Avdas Americas".
    x = re.sub(r"^(avenida|av|rua|r|alameda|estrada|estr|travessa|tv|praca|rodovia|largo)(?=(?:das|dos|do|da|de))", r"\1 ", x)

    street_types = r"(?:rua|r|avenida|av|alameda|estrada|estr|travessa|tv|praca|rodovia|largo)"
    titles = r"(?:professor|prof|doutor|doutora|dr|dra|engenheiro|engenheira|eng|coronel|cel|general|gen|capitao|capita|cap|major|maj|tenente|ten|sargento|sgt|prefeito)"

    # O nome oficial pode aparecer tanto "Prefeito Dulcídio Cardoso" quanto
    # "Dulcídio Cardoso, Prefeito". Removemos títulos só quando estão nas pontas.
    for _ in range(4):
        before = x
        x = re.sub(r"^(?:" + street_types + r"\s+)+", "", x)
        x = re.sub(r"^(?:" + titles + r"\s+)+", "", x)
        x = re.sub(r"[\s,]+(?:" + titles + r")$", "", x)
        x = re.sub(r"^(?:" + street_types + r"\s+)+", "", x)
        x = re.sub(r"\s+(?:rua|avenida|alameda|estrada|travessa|praca|rodovia|largo)$", "", x)
        x = re.sub(r"^(?:das|dos|da|do|de)\s+", "", x)
        x = re.sub(r"\s+", " ", x).strip(" ,")
        if x == before:
            break

    # Alias permanente: Lúcio Costa também é pesquisada como Sernambetiba.
    compact = re.sub(r"\s+", "", x)
    if compact in ("luciocosta", "avenidaluciocosta", "avluciocosta"):
        x = "sernambetiba"
    return re.sub(r"\s+", " ", x).strip()


def similarity_score(query, name):
    """Compara nomes aceitando erros de digitação e palavras extras no endereço."""
    if not query or not name:
        return 0
    if query == name:
        return 100
    q_compact = query.replace(" ", "")
    n_compact = name.replace(" ", "")
    compact_ratio = difflib.SequenceMatcher(None, q_compact, n_compact).ratio()
    full_ratio = difflib.SequenceMatcher(None, query, name).ratio()
    qt, nt = query.split(), name.split()

    def word_match(word, candidates):
        # Correspondência por palavra completa, inclusive pequenos erros de grafia.
        valid = [c for c in candidates if len(c) >= 3 and len(word) >= 3]
        if not valid:
            return 0
        return max(difflib.SequenceMatcher(None, word, c).ratio() for c in valid)

    # Pontuação tradicional: útil quando o nome inteiro é parecido.
    query_token_scores = [word_match(t, nt) for t in qt]
    token_ratio = sum(query_token_scores) / max(len(query_token_scores), 1)

    # NOVO: palavras extras como "Rua", "Professor", "Engenheiro" ou complemento
    # não devem impedir a busca quando todas as palavras principais da lista aparecem.
    candidate_scores = [word_match(t, qt) for t in nt]
    if candidate_scores and all(score >= 0.72 for score in candidate_scores):
        candidate_coverage = sum(candidate_scores) / len(candidate_scores)
        # Exige que nomes com várias palavras tenham correspondência em cada palavra.
        coverage_ratio = candidate_coverage * (0.98 if len(nt) >= 2 else 0.90)
    else:
        coverage_ratio = 0

    ratio = max(compact_ratio, full_ratio, token_ratio * 0.92, coverage_ratio)
    # Evita falsos positivos por coincidência com nomes de uma letra ou muito curtos.
    threshold = 0.76 if min(len(q_compact), len(n_compact)) >= 7 else 0.86
    if ratio < threshold:
        return 0
    return int(70 + min(ratio, 1.0) * 29)


def load_adjustments():
    try:
        with open(ADJUST_FILE, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict): return {"areas": {}, "oficiais": {}}
        data.setdefault("areas", {}); data.setdefault("oficiais", {})
        return data
    except (OSError, ValueError, TypeError):
        return {"areas": {}, "oficiais": {}}


def save_adjustments(data):
    with open(ADJUST_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def parse_records(adjustments=None):
    records = []
    if not os.path.exists(STREET_FILE):
        raise FileNotFoundError("Não encontrei lista_ruas_original.txt ao lado do programa.")
    pat = re.compile(r"^\s*N[°ºo]\s*([A-Z0-9]+)\s*\|\s*(.*?)\s*\|\s*ÁREA:\s*(.*?)\s*$", re.I)
    adjustments = adjustments or load_adjustments()
    with open(STREET_FILE, encoding="utf-8-sig") as f:
        for lineno, line in enumerate(f, 1):
            m = pat.match(line.strip())
            if not m:
                continue
            listing, name, area = m.groups()
            name, area = name.strip(), area.strip().rstrip(".")
            rule = ""
            rm = re.search(r"\((.*?)\)", name)
            if rm:
                paren_rule = rm.group(1).strip()
                before = name[:rm.start()].strip()
                after = name[rm.end():].strip()
                desc = re.search(r"\s+(?=(?:do\s+(?:in[ií]cio|\d)|apos\b|após\b|a partir|par\b|impar\b|ímpar\b|ate\b|até\b|\d{3,}(?:\s*(?:ao|a|ate|até)\b)?))", before, re.I)
                if desc:
                    clean_name = before[:desc.start()].strip()
                    rule = (before[desc.start():] + (" " + paren_rule if paren_rule else "") + (" " + after if after else "")).strip()
                else:
                    clean_name = re.sub(r"\s+", " ", before).strip()
                    paren_norm = norm(paren_rule)
                    is_parity_rule = bool(re.search(r"\b(?:par|impar)\b", paren_norm))
                    is_number_rule = bool(re.search(r"\d|a partir|restante|somente|apenas|númer|numero|ate|até|inicio|início|fim", paren_norm))
                    rule = paren_rule if (is_parity_rule or is_number_rule) else ""
                    if after:
                        # Complementos como "menos 4252" pertencem à regra da faixa,
                        # não ao nome da rua.
                        if rule and re.match(r"^(?:menos|exceto|mais|\+|a partir|ap[oó]s)(?:\s|$)", after, re.I):
                            rule = (rule + " " + after).strip()
                        else:
                            clean_name = (clean_name + " " + after).strip()
            else:
                desc = re.search(r"\s+(?=(?:do\s+(?:in[ií]cio|\d)|apos\b|após\b|a partir|par\b|impar\b|ímpar\b|ate\b|até\b|\d{3,}(?:\s*(?:ao|a|ate|até)\b)?))", name, re.I)
                if desc:
                    clean_name = name[:desc.start()].strip()
                    rule = name[desc.start():].strip()
                else:
                    desc = re.search(r",\s*(?=(?:do\s+(?:in[ií]cio|\d)|\d{3,}|par\b|impar\b|ímpar\b|ate\b|até\b))", name, re.I)
                    if desc:
                        clean_name = name[:desc.start()].strip()
                        rule = name[desc.start()+1:].strip()
                    else:
                        clean_name = name

            # Quando a separação começa em "nº 350", não deixe "nº" preso ao nome.
            clean_name = re.sub(r"\s*,?\s*(?:n[º°o.]?|n[uú]mero)\s*$", "", clean_name, flags=re.I)
            clean_name = re.sub(r"\s+", " ", clean_name).strip(" ,;:")
            rule = re.sub(r"\s+", " ", rule).strip()
            clean_area = adjustments.get("areas", {}).get(str(lineno), area if area and area not in ("—", "-") else "Não especificada no arquivo")
            records.append({"listing":listing.strip(), "name":name, "clean_name":clean_name,
                            "area":clean_area or "Não especificada no arquivo", "rule":rule,
                            "line":lineno, "nclean":norm(clean_name), "canonical":canonical_street(clean_name)})
    return records


def extract_number(address):
    # Primeiro número predial; aceita 17.100, nº 17100 e nome colado ao número.
    m = re.search(r"(?<![A-Za-zÀ-ÿ])\s+(\d[\d.]*)\b", address)
    if not m:
        m = re.search(r"[,;]\s*(\d[\d.]*)\b", address)
    if not m:
        # Fallback para entradas sem espaço/pontuação antes do número predial.
        m = re.search(r"([0-9][0-9.]*)\s*$", address.strip())
    if not m:
        return None
    try:
        return int(m.group(1).replace(".", ""))
    except ValueError:
        return None


def address_name(address):
    # Remove número predial inclusive quando foi colado ao nome da rua.
    m = re.search(r"(?<![A-Za-zÀ-ÿ])\s+\d[\d.]*\b|[,;]\s*\d[\d.]*\b", address)
    if not m:
        # Número final colado: ex. AvenidaDasAmericas17100.
        m = re.search(r"\d[\d.]*\s*$", address.strip())
    s = address[:m.start()] if m else address
    s = re.sub(r"[,;\s]+(?:n(?:[º°o.]|umero)?|numero)\s*$", "", s, flags=re.I)
    return canonical_street(s)


def _prepared_rule(rule):
    """Mantém os separadores de milhar e corrige palavras coladas a números."""
    raw = str(rule or "").strip()
    raw = re.sub(r"(?<=\d)\.(?=\d{3}(?:\D|$))", "", raw)
    raw = re.sub(r"(?<=\d)(?=[A-Za-zÀ-ÿ])", " ", raw)
    return raw, norm(raw)


def _rule_numbers(text):
    return [int(x) for x in re.findall(r"\d+", text or "")]


def _rule_exclusions(raw):
    """Retorna números/faixas explicitamente excluídos por 'menos' ou 'exceto'."""
    excluded = set()
    excluded_ranges = []
    for m in re.finditer(r"\b(?:menos|exceto|excepto)\b\s*(.*?)(?=\+|\bmais\b|$)", raw, re.I):
        clause = m.group(1).strip()
        nums = _rule_numbers(clause)
        if not nums:
            continue
        is_range = bool(re.search(r"\d\s*[-–—]\s*\d", clause)) or bool(re.search(r"\d+\s+(?:até|ate|ao|a)\s+\d+", norm(clause)))
        if is_range and len(nums) >= 2:
            excluded_ranges.append((min(nums[0], nums[1]), max(nums[0], nums[1])))
        else:
            excluded.update(nums)
    return excluded, excluded_ranges


def _rule_inclusions(raw):
    """Retorna os números adicionados expressamente com '+' ou 'mais'."""
    included = set()
    for marker in re.finditer(r"\+|\bmais\b", raw, re.I):
        tail = raw[marker.end():]
        tail = re.split(r"\b(?:menos|exceto|excepto)\b", tail, maxsplit=1, flags=re.I)[0]
        included.update(_rule_numbers(tail))
    return included


def _rule_evaluation(rule, number):
    """Devolve (resultado, prioridade); regras pontuais têm prioridade sobre faixas."""
    if not rule or number is None:
        return None, 0
    raw, r = _prepared_rule(rule)
    if not r:
        return None, 0

    # Compatibilidade com regras particulares da base.
    if "a partir do 800" in r and "315" in r:
        ok = number >= 800 or number == 315
        return (ok, 1 if ok else 0)
    if "a partir do 557" in r and "1006" in r:
        ok = number >= 557 and number != 1006
        return (ok, 1 if ok else 0)

    excluded, excluded_ranges = _rule_exclusions(raw)
    if number in excluded or any(lo <= number <= hi for lo, hi in excluded_ranges):
        return False, 0

    # Inclusões expressas são exceções à faixa-base e devem vencê-la.
    if number in _rule_inclusions(raw):
        return True, 3

    # Regras de números exclusivos: 5300; 120; 139, 271, 285; 350 + 380...
    # Não confundir com uma faixa, que sempre contém palavras de intervalo.
    has_range_syntax = bool(
        re.search(r"\bdo\s+inicio\b", r)
        or re.search(r"\b(?:ate|ao|a)\s+(?:o\s+)?(?:fim|final)\b", r)
        or re.search(r"\b(?:apos|a partir de|a partir do)\s+\d+", r)
        or re.search(r"\d+\s+(?:ate|ao|a)\s+(?:o\s+)?(?:n\s+)?\d+", r)
    )
    starts_with_number = bool(re.match(r"^\s*(?:n\s+)?\d+\b", r))
    if starts_with_number and not has_range_syntax:
        nums = set(_rule_numbers(raw))
        ok = number in nums
        return (ok, 3 if ok else 0)

    # Interpreta limites inferior e superior, inclusive faixas até o fim.
    low = high = None
    if "do inicio" in r:
        low = 0
        m = re.search(r"do inicio ate (?:o )?(?:n )?(\d+)", r)
        if m:
            high = int(m.group(1))
    else:
        m = re.search(r"(\d+)\s+(?:ate|ao|a)\s+(?:o\s+)?(?:n\s+)?(\d+)", r)
        if m:
            low, high = int(m.group(1)), int(m.group(2))
        else:
            m = re.search(r"(\d+)\s+(?:ate|ao|a)\s+(?:o\s+)?(?:fim|final)\b", r)
            if m:
                low = int(m.group(1))
            else:
                m = re.search(r"\bapos\s+(?:o\s+)?(?:n\s+)?(\d+)", r)
                if m:
                    low = int(m.group(1)) + 1
                else:
                    m = re.search(r"\ba partir (?:de|do)\s+(?:o\s+)?(?:n\s+)?(\d+)", r)
                    if m:
                        low = int(m.group(1))
                    else:
                        m = re.search(r"\bate\s+(?:o\s+)?(?:n\s+)?(\d+)", r)
                        if m:
                            high = int(m.group(1))

    has_range = low is not None or high is not None
    if has_range:
        if low is not None and number < low:
            return False, 0
        if high is not None and number > high:
            return False, 0

        has_even = bool(re.search(r"\bpar\b", r))
        has_odd = bool(re.search(r"\bimpar\b", r))
        if has_even and not has_odd and number % 2:
            return False, 0
        if has_odd and number % 2 == 0:
            return False, 0
        if low is not None and high is not None and not has_even and not has_odd and low % 2 == high % 2 and number % 2 != low % 2:
            return False, 0
        return True, 1

    # Regra de paridade pura ou outras descrições não interpretáveis.
    if r in ("par", "impar"):
        ok = (number % 2 == 0) if r == "par" else (number % 2 == 1)
        return (ok, 1 if ok else 0)
    return None, 0


def rule_matches(rule, number):
    """Confere faixa, paridade, listas pontuais e exceções explícitas."""
    return _rule_evaluation(rule, number)[0]


def rule_match_priority(rule, number):
    """Prioriza exceções/listas de números específicos sobre faixas genéricas."""
    verdict, priority = _rule_evaluation(rule, number)
    return priority if verdict is True else 0


def lookup(address, records, officials):
    number = extract_number(address)
    q = address_name(address)
    if not q:
        return {"status":"Não localizado", "address":address, "number":number, "results":[], "note":"Digite o nome da rua e, se houver, o número predial."}

    candidates = []
    for rec in records:
        nm = rec.get("canonical") or canonical_street(rec["clean_name"])
        if not nm:
            continue
        score = similarity_score(q, nm)
        if score:
            candidates.append((score, rec))

    if not candidates:
        return {"status":"Não localizado", "address":address, "number":number, "results":[], "note":"Não encontrei uma rua suficientemente parecida. Confira a grafia ou tente informar o nome sem abreviações."}

    best = max(score for score, _ in candidates)
    candidates = [rec for score, rec in candidates if best - score <= 2]

    # Para a mesma via, aplicamos primeiro a regra numérica. Números listados
    # explicitamente (+, mais ou lista pontual) prevalecem sobre a faixa geral.
    if number is not None and len(candidates) > 1:
        matches, residual, unknown = [], [], []
        for rec in candidates:
            verdict = rule_matches(rec["rule"], number)
            if verdict is True:
                if "restante da numeracao" in norm(rec["rule"]):
                    residual.append(rec)
                else:
                    matches.append(rec)
            elif verdict is None:
                unknown.append(rec)

        if matches:
            max_priority = max(rule_match_priority(rec["rule"], number) for rec in matches)
            if max_priority >= 2:
                candidates = [rec for rec in matches if rule_match_priority(rec["rule"], number) == max_priority]
            elif residual and not matches:
                candidates = residual
            else:
                candidates = matches
        elif residual:
            candidates = residual
        elif unknown:
            candidates = unknown
        else:
            return {"status":"Não confirmado", "address":address, "number":number, "results":candidates, "note":"Encontrei a rua, mas nenhuma regra de numeração cadastrada confirmou esse número. Confira as regras originais."}

    results=[]
    for rec in candidates:
        off = officials.get(str(rec["listing"]), {})
        adj = load_adjustments().get("oficiais", {}).get(str(rec["listing"]), {})
        if isinstance(adj, str): adj = {"nome":adj}
        results.append({"listing":rec["listing"], "street":rec["clean_name"], "area":rec["area"],
                        "official":adj.get("nome", off.get("nome", "Não consta na lista de oficiais")),
                        "period":adj.get("periodo", off.get("periodo", "")), "rule":rec["rule"], "source_line":rec["line"]})

    if len(results) > 1:
        status="Ambíguo — conferir"
        note="Encontrei mais de uma rua/listagem possível, inclusive por semelhança de escrita. Compare os resultados abaixo antes de escolher."
    else:
        r=results[0]
        verdict=rule_matches(r["rule"], number) if number is not None else None
        if number is not None and r["rule"] and verdict is False:
            status="Localizado — regra não confirma"
            note="A rua foi localizada, mas a regra cadastrada não confirma esse número: " + r["rule"]
        elif number is not None and r["rule"] and verdict is None:
            status="Localizado — conferir regra"
            note="Rua localizada por correspondência aproximada, mas não foi possível interpretar automaticamente a regra: " + r["rule"]
        elif number is not None and not r["rule"]:
            status="Localizado — conferir número"
            note="Rua localizada, mas a fonte não informa regra de numeração para confirmar esse número específico."
        else:
            status="Localizado"
            note="Correspondência localizada na lista (a busca aceita variações de escrita)."
        if r["area"] == "Não especificada no arquivo":
            note += " A área está em branco ou marcada com traço na fonte."
        if r["period"]:
            note += " Observação do oficial: " + r["period"] + "."
    return {"status":status, "address":address, "number":number, "results":results, "note":note}


def append_history(result):
    exists=os.path.exists(HISTORY_FILE)
    with open(HISTORY_FILE,"a",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f,delimiter=";")
        if not exists: w.writerow(["Data/hora","Endereço consultado","Status","Listagem","Rua/registro","Área","Oficial","Período/nota","Observações"])
        rows=result["results"] or [{"listing":"","street":"","area":"","official":"","period":""}]
        for r in rows:
            w.writerow([datetime.now().strftime("%d/%m/%Y %H:%M:%S"),result["address"],result["status"],r["listing"],r["street"],r["area"],r["official"],r["period"],result["note"]])


UI_FONT = "Segoe UI" if sys.platform == "win32" else "Arial"


COLORS = {
    "background": "#06152b", "panel": "#0b2344", "input": "#102d53",
    "border": "#1c4979", "text": "#f1f5ff", "muted": "#b0c4e4",
    "blue": "#1673ff", "cyan": "#58cfff", "teal": "#00cbb8",
}


def rounded_box(canvas, x1, y1, x2, y2, radius=12, **options):
    radius = max(0, min(radius, (x2-x1)/2, (y2-y1)/2))
    return canvas.create_polygon(
        x1+radius, y1, x2-radius, y1, x2, y1, x2, y1+radius,
        x2, y2-radius, x2, y2, x2-radius, y2, x1+radius, y2,
        x1, y2, x1, y2-radius, x1, y1+radius, x1, y1,
        smooth=True, splinesteps=24, **options)


def draw_icon(canvas, name, x, y, size=24, color="#b9d6ff", tag="icon"):
    """Small vector icons, independent of fonts and third-party packages."""
    scale = size/24
    def coords(points):
        return [v*scale + (x if i%2 == 0 else y) for i,v in enumerate(points)]
    def line(*points):
        canvas.create_line(*coords(points), fill=color, width=1.8*scale,
                           capstyle="round", joinstyle="round", tags=tag)
    def oval(*points):
        canvas.create_oval(*coords(points), outline=color, width=1.8*scale, tags=tag)
    def rectangle(*points):
        canvas.create_rectangle(*coords(points), outline=color, width=1.7*scale, tags=tag)
    if name == "search":
        oval(3, 3, 16, 16); line(15, 15, 22, 22)
    elif name == "clear":
        line(18, 2, 9, 13); line(7, 11, 15, 17, 10, 22, 2, 16, 7, 11)
        line(6, 16, 10, 19); line(4, 18, 7, 20)
    elif name == "map":
        line(2, 5, 8, 2, 16, 5, 22, 2, 22, 19, 16, 22, 8, 19, 2, 22, 2, 5)
        line(8, 2, 8, 19); line(16, 5, 16, 22)
    elif name == "users":
        oval(8, 2, 16, 10); line(5, 21, 5, 17, 8, 13, 16, 13, 19, 17, 19, 21, 5, 21)
        line(19, 4, 22, 6, 22, 10); line(21, 14, 23, 17, 23, 21)
        line(5, 4, 2, 6, 2, 10); line(3, 14, 1, 17, 1, 21)
    elif name == "info":
        oval(2, 2, 22, 22); line(12, 10, 12, 17); oval(11.5, 6, 12.5, 7)
    elif name == "folder":
        line(2, 6, 2, 21, 22, 21, 22, 7, 12, 7, 9, 3, 2, 3, 2, 6)
    elif name == "list":
        for row in (3, 10, 17):
            rectangle(2, row, 5, row+3); line(9, row+1.5, 22, row+1.5)
    elif name == "database":
        oval(3, 2, 21, 8); line(3, 5, 3, 19, 6, 22, 18, 22, 21, 19, 21, 5)
        line(3, 11, 7, 14, 17, 14, 21, 11); line(3, 16, 7, 19, 17, 19, 21, 16)
    elif name in ("file", "empty"):
        line(5, 2, 15, 2, 21, 8, 21, 22, 5, 22, 5, 2)
        line(15, 2, 15, 8, 21, 8)
        line(9, 11, 17, 11); line(9, 15, 16, 15); line(9, 18, 14, 18)
        if name == "empty":
            # The document/search symbol used in the empty state.
            canvas.create_rectangle(*coords((15, 13, 25, 25)), fill=COLORS["panel"], outline="", tags=tag)
            oval(16, 14, 24, 22); line(23, 21, 28, 26)


class BluePanel(tk.Canvas):
    def __init__(self, parent, height=100, padding=18):
        super().__init__(parent, height=height, bg=COLORS["background"],
                         bd=0, highlightthickness=0)
        self.padding = padding
        self.body = tk.Frame(self, bg=COLORS["panel"])
        self._window = self.create_window(padding, padding, window=self.body, anchor="nw")
        self.bind("<Configure>", self._resize)

    def _resize(self, event):
        self.delete("surface")
        rounded_box(self, 1, 1, event.width-1, event.height-1, 16,
                    fill=COLORS["panel"], outline=COLORS["border"], tags="surface")
        self.tag_lower("surface")
        self.itemconfigure(self._window, width=max(1, event.width-2*self.padding),
                           height=max(1, event.height-2*self.padding))


class BlueButton(tk.Canvas):
    def __init__(self, parent, text, command, icon, width=160, kind="normal"):
        super().__init__(parent, width=width, height=46, bd=0, highlightthickness=0,
                         bg=COLORS["panel"], cursor="hand2", takefocus=True)
        self.text, self.command, self.icon, self.kind = text, command, icon, kind
        self.hover = False
        self.bind("<Configure>", lambda event: self._draw())
        self.bind("<Enter>", lambda event: self._set_hover(True))
        self.bind("<Leave>", lambda event: self._set_hover(False))
        self.bind("<FocusIn>", lambda event: self._draw())
        self.bind("<FocusOut>", lambda event: self._draw())
        self.bind("<ButtonRelease-1>", self._click)
        self.bind("<Return>", self._activate)
        self.bind("<space>", self._activate)

    def _set_hover(self, active):
        self.hover = active
        self._draw()

    def _activate(self, event=None):
        self.command()
        return "break"

    def _click(self, event):
        if 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height():
            self.focus_set()
            self.command()

    def _draw(self):
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        palettes = {"normal": ("#102e58", "#193e6e", "#37639b"),
                    "primary": ("#0965fa", "#2581ff", "#56a4ff"),
                    "export": ("#063d49", "#07515b", "#00cbb8")}
        base, hover, border = palettes[self.kind]
        focused = self.focus_get() == self
        rounded_box(self, 1, 1, width-1, height-1, 9,
                    fill=hover if self.hover else base,
                    outline=COLORS["cyan"] if focused else border, width=1.5 if focused else 1)
        self.create_line(12, 3, width-12, 3, fill=border)
        # Center the icon and text as one group, also when the window shrinks.
        from tkinter import font as tkfont
        font = tkfont.Font(family=UI_FONT, size=10, weight="bold")
        if font.measure(self.text)+58 > width:
            font.configure(size=9)
        start = max(10, (width-font.measure(self.text)-36)/2)
        draw_icon(self, self.icon, start, (height-21)/2, 21,
                  "#73fff0" if self.kind == "export" else "#edf5ff")
        self.create_text(start+33, height/2, text=self.text, anchor="w", font=font, fill=COLORS["text"])


class App(tk.Tk):
    def __init__(self):
        super().__init__(); self.title(APP_TITLE)
        self.geometry(f"{min(1400, self.winfo_screenwidth()-60)}x{min(980, self.winfo_screenheight()-80)}")
        self.minsize(1060, 740)
        self.configure(bg=COLORS["background"])
        self._logo_image = None
        try:
            icon_path = os.path.join(BASE_DIR, "logo_mapa_documento.ico")
            if os.path.exists(icon_path): self.iconbitmap(icon_path)
        except Exception:
            pass
        try:
            self.adjustments=load_adjustments(); self.records=parse_records(self.adjustments)
            with open(OFFICIALS_FILE,encoding="utf-8") as f: self.officials=json.load(f)
        except Exception as e:
            messagebox.showerror("Erro ao carregar arquivos",str(e)); self.destroy(); return
        self.last_result=None; self._build()
        self.after(200,self.startup_check)

    def _configure_theme(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=COLORS["panel"], foreground=COLORS["text"],
                        font=(UI_FONT, 10), bordercolor=COLORS["border"],
                        lightcolor=COLORS["border"], darkcolor=COLORS["border"])
        style.configure("TFrame", background=COLORS["panel"])
        style.configure("TLabel", background=COLORS["panel"], foreground=COLORS["text"])
        style.configure("TButton", background="#173960", foreground=COLORS["text"],
                        padding=(12, 8), borderwidth=1)
        style.map("TButton", background=[("active", "#23508a")],
                  foreground=[("disabled", "#7188a8")])
        style.configure("TNotebook", background=COLORS["panel"])
        style.configure("TNotebook.Tab", background="#112d50", padding=(14, 8))
        style.map("TNotebook.Tab", background=[("selected", "#20518b")])
        style.configure("Treeview", background="#0a203d", fieldbackground="#0a203d",
                        foreground=COLORS["text"], rowheight=38, borderwidth=0,
                        font=(UI_FONT, 10))
        style.configure("Treeview.Heading", background="#14355d", foreground=COLORS["text"],
                        font=(UI_FONT, 10, "bold"), padding=(14, 13), relief="flat")
        style.map("Treeview.Heading", background=[("active", "#1b4375")])
        style.map("Treeview", background=[("selected", "#1759a0")],
                  foreground=[("selected", "#ffffff")])
        style.configure("Vertical.TScrollbar", background="#254a76", troughcolor="#0a203d",
                        arrowcolor="#89aad7", borderwidth=0, arrowsize=13)
        style.configure("Horizontal.TScrollbar", background="#254a76", troughcolor="#0a203d",
                        arrowcolor="#89aad7", borderwidth=0, arrowsize=13)
        for scrollbar_style in ("Vertical.TScrollbar", "Horizontal.TScrollbar"):
            style.map(scrollbar_style, background=[("disabled", "#0a203d"), ("active", "#376ba5")],
                      arrowcolor=[("disabled", "#0a203d")])
        self.option_add("*Toplevel.background", COLORS["panel"])
        self.option_add("*Dialog.background", COLORS["panel"])
        self.option_add("*Entry.background", COLORS["input"])
        self.option_add("*Entry.foreground", COLORS["text"])
        self.option_add("*Entry.insertBackground", COLORS["text"])

    def _draw_header(self, event):
        canvas = self.header
        canvas.delete("all")
        width, height = event.width, event.height
        # An original vector illustration of Rio; it stays sharp offline.
        for row in range(height):
            t = row/max(1, height-1)
            rgb = tuple(round(a+(b-a)*t) for a,b in zip((14, 54, 105), (6, 21, 43)))
            canvas.create_line(0, row, width, row, fill="#%02x%02x%02x" % rgb)
        def landscape(points, fill, smooth=True):
            canvas.create_polygon(*[v*(width if i%2 == 0 else height) for i,v in enumerate(points)],
                                  fill=fill, outline="", smooth=smooth, splinesteps=20)
        landscape((.44, 1, .48, .52, .54, .66, .60, .30, .67, .57, .74, .28,
                   .82, .42, .91, .18, 1, .36, 1, 1), "#103c70")
        landscape((.51, 1, .61, .68, .68, .84, .73, .58, .79, .77, .87, .42,
                   .95, .67, 1, .53, 1, 1), "#0c2c55")
        # Sugarloaf Mountain and the Corcovado silhouette.
        landscape((.64, 1, .67, .76, .70, .62, .721, .20, .739, .18,
                   .757, .63, .79, .83, .84, 1), "#092344")
        landscape((.81, 1, .88, .71, .923, .52, .958, .74, 1, .86, 1, 1), "#071e3b")
        cx, cy = width*.924, height*.34
        ink = "#061b35"
        canvas.create_oval(cx-4, cy-18, cx+4, cy-10, fill=ink, outline="")
        canvas.create_polygon(cx-6, cy-9, cx-29, cy-12, cx-30, cy-7,
                              cx-7, cy-1, cx-5, cy+25, cx+5, cy+25,
                              cx+7, cy-1, cx+30, cy-7, cx+29, cy-12, cx+6, cy-9,
                              fill=ink)
        for i in range(56):
            x = width*(.55+i*.008)
            building = 4+(i*13 % 17)
            canvas.create_rectangle(x, height-building, x+5, height, fill="#092746", outline="")
        if self._logo_image:
            canvas.create_image(32, height/2, image=self._logo_image, anchor="w")
        canvas.create_line(161, 38, 161, height-36, fill="#406593")
        title_size = 26 if width >= 1250 else 23 if width >= 1120 else 20
        canvas.create_text(192, height/2-17, text=APP_TITLE, anchor="w",
                           fill=COLORS["text"], font=(UI_FONT, title_size, "bold"))
        canvas.create_text(193, height/2+27,
                           text="Funciona offline  ·  Base de dados local  ·  Consulta rápida e confiável",
                           anchor="w", fill=COLORS["muted"], font=(UI_FONT, 12))

    def _build(self):
        self._configure_theme()
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        logo_path = os.path.join(BASE_DIR, "logo_mapa_documento.png")
        if os.path.exists(logo_path):
            try:
                logo = tk.PhotoImage(file=logo_path)
                self._logo_image = logo.subsample(max(1, round(logo.width()/104)))
                # Render the white outer corners of the supplied logo transparently.
                # The source asset itself is left unchanged.
                image_width, image_height = self._logo_image.width(), self._logo_image.height()
                pending = [(x, y) for x in range(image_width) for y in (0, image_height-1)]
                pending += [(x, y) for x in (0, image_width-1) for y in range(image_height)]
                seen = set()
                while pending:
                    x, y = pending.pop()
                    if (x, y) in seen or not (0 <= x < image_width and 0 <= y < image_height):
                        continue
                    seen.add((x, y))
                    if min(self._logo_image.get(x, y)) > 235:
                        self._logo_image.transparency_set(x, y, True)
                        pending.extend(((x-1, y), (x+1, y), (x, y-1), (x, y+1)))
                self.iconphoto(True, self._logo_image)
            except tk.TclError:
                self._logo_image = None
        self.header = tk.Canvas(self, height=156, bg=COLORS["background"],
                                bd=0, highlightthickness=0)
        self.header.grid(row=0, column=0, sticky="ew")
        self.header.bind("<Configure>", self._draw_header)
        def resize_window(event):
            if event.widget == self:
                self.header.configure(height=132 if event.height < 820 else 156)
        self.bind("<Configure>", resize_window)

        search_panel = BluePanel(self, height=120, padding=20)
        search_panel.grid(row=1, column=0, sticky="ew", padx=24, pady=(0, 14))
        search = search_panel.body
        search.grid_columnconfigure(0, weight=1)
        tk.Label(search, text="Endereço completo", bg=COLORS["panel"], fg=COLORS["text"],
                 font=(UI_FONT, 11, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))
        search_row = tk.Frame(search, bg=COLORS["panel"])
        search_row.grid(row=1, column=0, sticky="ew")
        search_row.grid_columnconfigure(0, weight=1)
        self.search_field = tk.Frame(search_row, bg=COLORS["input"], highlightthickness=1,
                                     highlightbackground="#6382ae", height=46)
        self.search_field.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        self.search_field.grid_columnconfigure(1, weight=1)
        search_icon = tk.Canvas(self.search_field, width=44, height=42, bg=COLORS["input"],
                                bd=0, highlightthickness=0)
        search_icon.grid(row=0, column=0)
        draw_icon(search_icon, "search", 13, 11, 21)
        self.query = tk.StringVar()
        self.entry = tk.Entry(self.search_field, textvariable=self.query, bg=COLORS["input"],
                              fg=COLORS["text"], insertbackground="#ffffff", selectbackground="#216bd0",
                              relief="flat", bd=0, highlightthickness=0, font=(UI_FONT, 12))
        self.entry.grid(row=0, column=1, sticky="ew", padx=(2, 14))
        self.entry.bind("<Return>", lambda event: self.do_lookup())
        self.placeholder = tk.Label(self.search_field, text="Digite o endereço completo para consultar...",
                                    bg=COLORS["input"], fg="#9eb7da", font=(UI_FONT, 11), cursor="xterm")
        self.placeholder.place(x=47, rely=.5, anchor="w")
        self.placeholder.bind("<Button-1>", lambda event: self.entry.focus_set())
        self.entry.bind("<FocusIn>", self._search_focus)
        self.entry.bind("<FocusOut>", self._search_focus)
        self.query.trace_add("write", lambda *args: self._update_placeholder())
        self.consult_button = BlueButton(search_row, "Consultar", self.do_lookup, "search", width=170, kind="primary")
        self.consult_button.grid(row=0, column=1, sticky="ns", padx=(0, 12))
        self.clear_button = BlueButton(search_row, "Limpar", self.clear, "clear", width=134)
        self.clear_button.grid(row=0, column=2, sticky="ns")

        status_panel = BluePanel(self, height=88, padding=16)
        status_panel.grid(row=2, column=0, sticky="ew", padx=24, pady=(0, 14))
        status_body = status_panel.body
        status_body.grid_columnconfigure(2, weight=1)
        info = tk.Canvas(status_body, width=50, height=50, bg=COLORS["panel"], bd=0, highlightthickness=0)
        info.grid(row=0, column=0, rowspan=2, padx=(0, 12))
        draw_icon(info, "info", 8, 9, 32, "#68a3ff")
        tk.Frame(status_body, bg="#2b5687", width=1).grid(row=0, column=1, rowspan=2, sticky="ns", padx=(0, 16))
        self.status = tk.Label(status_body, text="Pronto para consultar.", bg=COLORS["panel"],
                               fg=COLORS["text"], font=(UI_FONT, 10, "bold"), anchor="w")
        self.status.grid(row=0, column=2, sticky="ew", pady=(1, 2))
        self.note = tk.Text(status_body, height=2, bg=COLORS["panel"], fg=COLORS["muted"],
                            relief="flat", bd=0, highlightthickness=0, wrap="word", font=(UI_FONT, 9),
                            padx=0, pady=0, cursor="arrow", takefocus=False)
        self.note.grid(row=1, column=2, sticky="ew")
        self.set_note("Digite um endereço e clique em Consultar.")

        results_panel = BluePanel(self, height=320, padding=16)
        results_panel.grid(row=3, column=0, sticky="nsew", padx=24, pady=(0, 14))
        results = results_panel.body
        results.grid_columnconfigure(0, weight=1)
        results.grid_rowconfigure(1, weight=1)
        heading = tk.Frame(results, bg=COLORS["panel"])
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        list_icon = tk.Canvas(heading, width=36, height=30, bg=COLORS["panel"], bd=0, highlightthickness=0)
        list_icon.pack(side="left", padx=(4, 10))
        draw_icon(list_icon, "list", 3, 3, 25, "#589eff")
        tk.Label(heading, text="Correspondências encontradas", bg=COLORS["panel"], fg=COLORS["text"],
                 font=(UI_FONT, 13, "bold")).pack(side="left")
        self.result_count = tk.StringVar(value="0 registros")
        tk.Label(heading, textvariable=self.result_count, bg="#14375e", fg="#c4dbff", padx=14, pady=5,
                 font=(UI_FONT, 9)).pack(side="right", padx=(0, 4))
        table = tk.Frame(results, bg=COLORS["panel"], highlightthickness=1, highlightbackground=COLORS["border"])
        table.grid(row=1, column=0, sticky="nsew")
        table.grid_columnconfigure(0, weight=1)
        table.grid_rowconfigure(0, weight=1)
        cols = ("listing", "street", "area", "official", "period", "rule")
        labels = {"listing":"Listagem", "street":"Rua/registro", "area":"Bairro / Área",
                  "official":"Oficial", "period":"Período/nota", "rule":"Regra de numeração"}
        widths = {"listing":100, "street":250, "area":220, "official":170, "period":160, "rule":230}
        minimums = {"listing":100, "street":170, "area":170, "official":120, "period":130, "rule":190}
        self.tree = ttk.Treeview(table, columns=cols, show="headings", height=6)
        for col in cols:
            self.tree.heading(col, text=labels[col], anchor="w")
            self.tree.column(col, width=widths[col], minwidth=minimums[col], stretch=True, anchor="w")
        self.tree.tag_configure("even", background="#0c2547")
        self.tree.tag_configure("odd", background="#102e50")
        y = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        x = ttk.Scrollbar(table, orient="horizontal", command=self.tree.xview)
        def update_scrollbar(scrollbar, first, last):
            scrollbar.set(first, last)
            if float(first) <= 0 and float(last) >= 1:
                scrollbar.grid_remove()
            else:
                scrollbar.grid()
        self.tree.configure(yscrollcommand=lambda first, last: update_scrollbar(y, first, last),
                            xscrollcommand=lambda first, last: update_scrollbar(x, first, last))
        self.tree.grid(row=0, column=0, sticky="nsew")
        y.grid(row=0, column=1, sticky="ns")
        x.grid(row=1, column=0, sticky="ew")
        self.empty_state = tk.Frame(table, bg="#0a203d")
        empty_content = tk.Frame(self.empty_state, bg="#0a203d")
        empty_content.place(relx=.5, rely=.5, anchor="center")
        empty_icon = tk.Canvas(empty_content, width=78, height=64, bg="#0a203d", bd=0, highlightthickness=0)
        empty_icon.pack(pady=(0, 12))
        draw_icon(empty_icon, "empty", 4, 1, 53, "#507eb8")
        empty_title = tk.Label(empty_content, text="Nenhum resultado para exibir.", bg="#0a203d", fg="#c6d8f5",
                               font=(UI_FONT, 12))
        empty_title.pack()
        tk.Label(empty_content, text="Realize uma consulta para mostrar as correspondências.",
                 bg="#0a203d", fg=COLORS["muted"], font=(UI_FONT, 10)).pack(pady=(8, 0))
        self._position_empty()

        footer_panel = BluePanel(self, height=132, padding=20)
        footer_panel.grid(row=4, column=0, sticky="ew", padx=24, pady=(0, 18))
        footer = footer_panel.body
        footer.grid_columnconfigure(0, weight=1)
        actions = tk.Frame(footer, bg=COLORS["panel"])
        actions.grid(row=0, column=0, sticky="ew")
        for col, weight in enumerate((24, 12, 13, 20, 23)):
            actions.grid_columnconfigure(col, weight=weight, uniform="actions")
        self.action_buttons = []
        for col, (label, command, icon, kind) in enumerate((
            ("Exportar relatório em texto", self.export_history, "file", "export"),
            ("ÁREAS", self.change_region_with_instructions, "map", "normal"),
            ("OFICIAIS", self.edit_officials, "users", "normal"),
            ("Sobre o programa", self.about_program, "info", "normal"),
            ("Abrir pasta do programa", self.show_folder, "folder", "normal"),
        )):
            button = BlueButton(actions, label, command, icon, width=1, kind=kind)
            button.grid(row=0, column=col, sticky="ew", padx=(0 if col == 0 else 6, 0 if col == 4 else 6))
            self.action_buttons.append(button)
        hint = tk.Frame(footer, bg=COLORS["panel"])
        hint.grid(row=1, column=0, sticky="ew", pady=(12, 0))
        hint_icon = tk.Canvas(hint, width=30, height=36, bg=COLORS["panel"], bd=0, highlightthickness=0)
        hint_icon.pack(side="left", padx=(0, 12))
        draw_icon(hint_icon, "database", 2, 5, 23, "#8ca8ce")
        tk.Label(hint, text="Cada consulta é registrada automaticamente no relatório local.\nAo terminar, clique em Exportar relatório. Confirme os casos sinalizados na lista original.",
                 bg=COLORS["panel"], fg=COLORS["muted"], justify="left", font=(UI_FONT, 9)).pack(side="left")
        self.signature = tk.Label(hint, text="Desenvolvido por ALEXANDRE RAMOS ZANARDI © 2026",
                                  bg=COLORS["panel"], fg="#9db5d8", font=(UI_FONT, 8))
        self.signature.pack(side="right", anchor="s")
        # Keep the attribution visible on smaller monitors, without crowding help text.
        def resize_footer(event):
            if event.width < 1200:
                footer_panel.configure(height=158)
                self.signature.pack_forget()
                self.signature_small.grid()
            else:
                footer_panel.configure(height=132)
                self.signature.pack(side="right", anchor="s")
                self.signature_small.grid_remove()
        self.signature_small = tk.Label(footer, text="Desenvolvido por ALEXANDRE RAMOS ZANARDI © 2026",
                                        bg=COLORS["panel"], fg="#9db5d8", font=(UI_FONT, 8))
        self.signature_small.grid(row=2, column=0, sticky="e", pady=(3, 0))
        self.signature_small.grid_remove()
        footer.bind("<Configure>", resize_footer)

        def resize_empty(event):
            if event.height < 180:
                empty_icon.pack_forget()
            elif not empty_icon.winfo_manager():
                empty_icon.pack(before=empty_title, pady=(0, 12))
        self.empty_state.bind("<Configure>", resize_empty)
        self.tree.bind("<Configure>", lambda event: self._position_empty() if not self.tree.get_children() else None)

    def _search_focus(self, event):
        self.search_field.configure(highlightbackground=COLORS["cyan"] if event.type == tk.EventType.FocusIn else "#6382ae")
        self._update_placeholder()

    def _update_placeholder(self):
        if self.query.get() or self.focus_get() == self.entry:
            self.placeholder.place_forget()
        else:
            self.placeholder.place(x=47, rely=.5, anchor="w")

    def _refresh_results(self):
        count = len(self.tree.get_children())
        self.result_count.set(f"{count} registro" if count == 1 else f"{count} registros")
        if count:
            self.empty_state.place_forget()
        else:
            self._position_empty()

    def _position_empty(self):
        heading_height = 48
        for y in range(min(80, self.tree.winfo_height())):
            if self.tree.identify_region(20, y) == "heading":
                heading_height = y+1
        self.empty_state.place(in_=self.tree, x=1, y=heading_height, relwidth=1, width=-2,
                               relheight=1, height=-heading_height-1)

    def startup_check(self):
        if messagebox.askyesno("Conferir alterações","Deseja conferir os dados dos oficiais antes de pesquisar?\n\nSim: abrir a opção OFICIAIS.\nNão: começar a consultar."):
            self.edit_officials()

    def set_note(self,text):
        self.note.configure(state="normal"); self.note.delete("1.0","end"); self.note.insert("1.0",text); self.note.configure(state="disabled")

    def do_lookup(self):
        address=self.query.get().strip()
        if not address: messagebox.showinfo("Endereço","Digite o nome da rua e o número predial, se houver."); return
        self.adjustments=load_adjustments(); self.records=parse_records(self.adjustments)
        self.last_result=lookup(address,self.records,self.officials); self.status.configure(text=self.last_result["status"]); self.set_note(self.last_result["note"])
        append_history(self.last_result)
        for i in self.tree.get_children(): self.tree.delete(i)
        for index, r in enumerate(self.last_result["results"]):
            self.tree.insert("","end",values=(r["listing"],r["street"],r["area"],r["official"],r["period"],r["rule"]),
                             tags=("even" if index % 2 == 0 else "odd",))
        self._refresh_results()
        if self.last_result["results"] and len(self.last_result["results"])==1:
            r=self.last_result["results"][0]; self.status.configure(text=self.last_result["status"]+" | Bairro/Área: "+r["area"]+" | Listagem "+r["listing"]+" | "+r["official"])

    def save_current(self):
        if not self.last_result: messagebox.showinfo("Relatório","Faça uma consulta primeiro."); return
        append_history(self.last_result); messagebox.showinfo("Relatório","Consulta registrada. Continue consultando e registre cada endereço; ao final, exporte o relatório.")

    def export_history(self):
        """Exporta todas as consultas com o endereço digitado e o oficial ao lado."""
        if not os.path.exists(HISTORY_FILE):
            messagebox.showinfo("Exportação", "Ainda não há consultas registradas. Faça consultas primeiro.")
            return
        path=filedialog.asksaveasfilename(
            title="Salvar relatório em texto",
            defaultextension=".txt",
            filetypes=[("Arquivo de texto", "*.txt"), ("Todos os arquivos", "*.*")],
            initialfile="relatorio_ruas_oficiais.txt"
        )
        if not path:
            return
        try:
            lines=["RELATÓRIO DE RUAS E OFICIAIS", ""]
            seen=set()
            with open(HISTORY_FILE, "r", newline="", encoding="utf-8-sig") as src:
                reader=csv.DictReader(src, delimiter=";")
                for row in reader:
                    # O relatório deve preservar exatamente o endereço digitado,
                    # incluindo número, bloco, sala, apartamento e outros complementos.
                    address=(row.get("Endereço consultado") or "").strip()
                    official=(row.get("Oficial") or "").strip()
                    if not address:
                        continue
                    entry=(address.casefold(), official.casefold())
                    if entry in seen:
                        continue
                    seen.add(entry)
                    lines.append(f"{address} — {official if official else 'Oficial não identificado'}")
            if len(lines) == 2:
                messagebox.showinfo("Exportação", "Não há endereços consultados registrados no histórico.")
                return
            with open(path, "w", encoding="utf-8-sig") as dst:
                dst.write("\n".join(lines) + "\n")
            messagebox.showinfo("Exportação", "Relatório em texto simples salvo com os endereços completos pesquisados e os oficiais ao lado.")
        except Exception as e:
            messagebox.showerror("Erro na exportação", f"Não foi possível salvar o relatório.\n\n{e}")

    def change_region_with_instructions(self):
        """Explica como localizar a lista atual antes de iniciar a troca de região."""
        instructions = (
            "COMO ALTERAR A ÁREA\n\n"
            "1. Abra o Bloco de Notas.\n"
            "2. Clique em Arquivo → Abrir.\n"
            "3. Navegue até a pasta do programa e localize o arquivo "
            "lista_ruas_original.txt.\n"
            "4. Nesse arquivo, você irá colocar a lista da nova área.\n\n"
            "Clique em OK para continuar ou em Cancelar para voltar."
        )
        if messagebox.askokcancel("ÁREAS", instructions, parent=self):
            self.import_region_base()

    def import_region_base(self):
        """Substitui a base ativa por uma lista de ruas/áreas e oficiais de outra região."""
        street_path = filedialog.askopenfilename(
            title="Selecione a lista de ruas e áreas da nova região",
            filetypes=[("Lista de ruas e áreas", "*.txt"), ("Todos os arquivos", "*.*")])
        if not street_path:
            return
        try:
            with open(street_path, encoding="utf-8-sig") as f:
                content = f.read()
            pattern = re.compile(r"^\s*N[°ºo]\s*([A-Z0-9]+)\s*\|\s*(.*?)\s*\|\s*ÁREA:\s*(.*?)\s*$", re.I | re.M)
            count = len(pattern.findall(content))
            if count == 0:
                messagebox.showerror("Formato não reconhecido",
                    "O arquivo escolhido não contém registros no formato esperado.\n\n"
                    "Cada linha deve seguir este padrão: N° 1 | Nome da rua (regra, se houver) | ÁREA: Nome da área\n\n"
                    "Nenhum arquivo foi alterado.", parent=self)
                return
            officials_path = filedialog.askopenfilename(
                title="Selecione o arquivo de oficiais da mesma região (JSON)",
                filetypes=[("Cadastro de oficiais (JSON)", "*.json"), ("Todos os arquivos", "*.*")])
            if not officials_path:
                messagebox.showinfo("Importação cancelada", "Selecione também o arquivo JSON dos oficiais para manter a base completa. Nenhum arquivo foi alterado.", parent=self)
                return
            with open(officials_path, encoding="utf-8-sig") as f:
                new_officials = json.load(f)
            if not isinstance(new_officials, dict) or not new_officials:
                raise ValueError("O arquivo de oficiais deve ser um JSON com listagens e dados dos oficiais.")
            # Testa se o JSON contém registros utilizáveis antes de substituir os arquivos ativos.
            for key, value in new_officials.items():
                if not isinstance(value, dict) or not (value.get("nome") or value.get("official")):
                    raise ValueError(f"O registro de oficial '{key}' não possui um campo 'nome'.")
            if not messagebox.askyesno("Confirmar troca de base",
                f"A nova base contém {count} registros de ruas/áreas.\n"
                f"Serão usados os oficiais do arquivo selecionado.\n\n"
                "O programa guardará cópias da base atual antes da troca.\n"
                "Os ajustes manuais de áreas/oficiais serão reiniciados para evitar aplicar regras antigas às ruas novas.\n\n"
                "Deseja continuar?", parent=self):
                return
            backup_dir = os.path.join(BASE_DIR, "bases_anteriores", datetime.now().strftime("%Y%m%d_%H%M%S"))
            os.makedirs(backup_dir, exist_ok=True)
            for active in (STREET_FILE, OFFICIALS_FILE, ADJUST_FILE, AREAS_FILE):
                if os.path.isfile(active):
                    shutil.copy2(active, os.path.join(backup_dir, os.path.basename(active)))
            # Valida tudo em memória antes da escrita; salva também o nome de região selecionada.
            with open(STREET_FILE, "w", encoding="utf-8") as f:
                f.write(content)
            with open(OFFICIALS_FILE, "w", encoding="utf-8") as f:
                json.dump(new_officials, f, ensure_ascii=False, indent=2)
            save_adjustments({"areas": {}, "oficiais": {}})
            with open(AREAS_FILE, "w", encoding="utf-8") as f:
                json.dump({"areas": sorted({m[2].strip() for m in pattern.findall(content) if m[2].strip()}, key=str.casefold)}, f, ensure_ascii=False, indent=2)
            self.adjustments = load_adjustments()
            self.records = parse_records(self.adjustments)
            with open(OFFICIALS_FILE, encoding="utf-8") as f:
                self.officials = json.load(f)
            for item in self.tree.get_children():
                self.tree.delete(item)
            self._refresh_results()
            self.last_result = None
            self.status.configure(text=f"Nova base carregada: {len(self.records)} registros disponíveis.")
            self.set_note("A consulta agora utiliza a nova base importada.")
            messagebox.showinfo("Base atualizada",
                f"Nova base carregada com {len(self.records)} registros.\n\n"
                f"A base anterior foi preservada em:\n{backup_dir}\n\n"
                "Faça consultas de teste para confirmar áreas, oficiais e regras de numeração.", parent=self)
        except Exception as e:
            messagebox.showerror("Erro ao importar base", f"Não foi possível importar a nova região.\n\n{e}", parent=self)

    def edit_officials(self):
        """Tela independente para manter os nomes e observações dos oficiais."""
        win=tk.Toplevel(self); win.title("OFICIAIS"); win.geometry("760x520"); win.transient(self)
        ttk.Label(win,text="Cadastre ou atualize o nome e o período/observação de cada oficial.").pack(anchor="w",padx=12,pady=(12,8))
        cols=("listing","official","period"); tree=ttk.Treeview(win,columns=cols,show="headings",height=16)
        for c,label,w in (("listing","Listagem",90),("official","Oficial",250),("period","Período / observação",320)):
            tree.heading(c,text=label); tree.column(c,width=w)
        tree.pack(fill="both",expand=True,padx=12)
        adj=load_adjustments().get("oficiais",{})
        for key in sorted(set(self.officials)|set(adj),key=lambda x:(not x.isdigit(),int(x) if x.isdigit() else x)):
            base=self.officials.get(str(key),{}); override=adj.get(str(key),{})
            if isinstance(override,str): override={"nome":override}
            tree.insert("","end",iid=str(key),values=(key,override.get("nome",base.get("nome","")),override.get("periodo",base.get("periodo",""))))
        def edit_selected():
            sel=tree.selection()
            if not sel: messagebox.showinfo("OFICIAIS","Selecione uma listagem.",parent=win); return
            key=sel[0]; vals=tree.item(key,"values")
            name=simpledialog.askstring("Nome do oficial",f"Oficial da listagem {key}:",initialvalue=vals[1],parent=win)
            if name is None:return
            period=simpledialog.askstring("Período / observação","Período ou observação (pode deixar em branco):",initialvalue=vals[2],parent=win)
            if period is not None: tree.item(key,values=(key,name.strip(),period.strip()))
        def save():
            current=load_adjustments(); current.setdefault("oficiais",{}); current.setdefault("areas",{})
            for key in tree.get_children():
                vals=tree.item(key,"values"); base=self.officials.get(str(key),{})
                if vals[1].strip()!=base.get("nome","") or vals[2].strip()!=base.get("periodo",""):
                    current["oficiais"][str(key)]={"nome":vals[1].strip(),"periodo":vals[2].strip()}
                else: current["oficiais"].pop(str(key),None)
            save_adjustments(current); self.adjustments=current
            messagebox.showinfo("OFICIAIS","Dados dos oficiais salvos.",parent=win); win.destroy()
        controls=ttk.Frame(win); controls.pack(fill="x",padx=12,pady=10)
        ttk.Button(controls,text="Editar selecionado",command=edit_selected).pack(side="left")
        ttk.Button(controls,text="Salvar alterações",command=save).pack(side="right")

    def edit_areas_catalog(self):
        """Mostra as áreas reais da base e permite renomeá-las globalmente."""
        win=tk.Toplevel(self); win.title("ÁREAS"); win.geometry("760x560"); win.transient(self)
        ttk.Label(win,text=("Esta é a lista de áreas encontrada nos registros originais. "
            "Ao renomear uma área, a alteração será aplicada a todas as ruas que usam esse nome.\n"
            "Para cadastrar uma região nova, também é necessário cadastrar/importar suas ruas e associar cada rua à área correta."),
            wraplength=720,justify="left").pack(anchor="w",padx=12,pady=(12,8))
        cols=("original","atual")
        tree=ttk.Treeview(win,columns=cols,show="headings",height=17)
        tree.heading("original",text="Área na base original")
        tree.heading("atual",text="Área usada nas consultas")
        tree.column("original",width=330); tree.column("atual",width=350)
        tree.pack(fill="both",expand=True,padx=12)
        records=parse_records(load_adjustments())
        base_records=parse_records({"areas":{},"oficiais":{}})
        originals=sorted({r["area"] for r in base_records if r["area"] and r["area"]!="Não especificada no arquivo"},key=str.casefold)
        # Reconstroi a área atual pela primeira ocorrência de cada área original.
        current_adjustments=load_adjustments().get("areas",{})
        current_by_original={}
        for rec in base_records:
            original=rec["area"]
            if original in originals and original not in current_by_original:
                current_by_original[original]=original
            adjusted=current_adjustments.get(str(rec["line"]))
            if adjusted and original in originals:
                current_by_original[original]=adjusted
        for original in originals:
            tree.insert("","end",iid=str(len(tree.get_children())),values=(original,current_by_original.get(original,original)))
        def edit_selected():
            sel=tree.selection()
            if not sel:
                messagebox.showinfo("ÁREAS","Selecione uma área para alterar.",parent=win); return
            vals=tree.item(sel[0],"values")
            new_name=simpledialog.askstring("Renomear área",f"Novo nome para a área '{vals[1]}':",initialvalue=vals[1],parent=win)
            if new_name is not None and new_name.strip():
                tree.set(sel[0],"atual",new_name.strip())
        def save_areas():
            current=load_adjustments(); current.setdefault("areas",{}); current.setdefault("oficiais",{})
            rename={}
            for key in tree.get_children():
                original,updated=tree.item(key,"values")
                if updated.strip(): rename[original]=updated.strip()
            # Aplicar o nome escolhido a todos os registros da área original,
            # preservando áreas individuais que já tenham sido ajustadas manualmente.
            for rec in base_records:
                original=rec["area"]
                if original in rename:
                    desired=rename[original]
                    if desired != original:
                        current["areas"][str(rec["line"])]=desired
                    else:
                        current["areas"].pop(str(rec["line"]),None)
            save_adjustments(current)
            # Mantém um catálogo atualizado para consulta/edição posterior.
            catalog=sorted({v for v in rename.values() if v},key=str.casefold)
            with open(AREAS_FILE,"w",encoding="utf-8") as f:
                json.dump({"areas":catalog},f,ensure_ascii=False,indent=2)
            self.adjustments=load_adjustments(); self.records=parse_records(self.adjustments)
            messagebox.showinfo("ÁREAS", "Áreas atualizadas. As próximas consultas já usarão os nomes novos.",parent=win)
            win.destroy()
        controls=ttk.Frame(win); controls.pack(fill="x",padx=12,pady=10)
        ttk.Button(controls,text="Renomear área selecionada",command=edit_selected).pack(side="left")
        ttk.Button(controls,text="Salvar alterações",command=save_areas).pack(side="right")

    def about_program(self):
        win=tk.Toplevel(self); win.title("Sobre o programa"); win.geometry("540x390"); win.resizable(False,False); win.transient(self)
        body=ttk.Frame(win,padding=20); body.pack(fill="both",expand=True)
        ttk.Label(body,text=APP_TITLE,font=(UI_FONT,16,"bold")).pack(anchor="w",pady=(0,12))
        description=("FINALIDADE\nEste programa auxilia na consulta de endereços, ruas, áreas de atendimento e respectivos oficiais, utilizando bases de dados cadastradas localmente.\n\n"
                     "COMO FUNCIONA\nCruza o endereço informado com os registros disponíveis, considerando nomes de vias, áreas, faixas de numeração e regras específicas cadastradas. A busca tolera variações comuns de escrita e complementos como bloco e apartamento.\n\n"
                     "FUNCIONAMENTO OFFLINE\nPode ser utilizado sem conexão com a internet, desde que os arquivos de dados estejam disponíveis no computador.\n\n"
                     "AUTORIA\nDesenvolvido por ALEXANDRE RAMOS ZANARDI © 2026")
        ttk.Label(body,text=description,wraplength=490,justify="left").pack(anchor="w",fill="x")
        ttk.Button(body,text="Fechar",command=win.destroy).pack(anchor="e",pady=(18,0))

    def edit_data(self):
        win=tk.Toplevel(self); win.title("Revisar áreas e oficiais"); win.geometry("900x600"); win.transient(self)
        book=ttk.Notebook(win); book.pack(fill="both",expand=True,padx=10,pady=10)
        # Tab officials
        tab1=ttk.Frame(book,padding=10); book.add(tab1,text="Oficiais por listagem")
        ttk.Label(tab1,text="Selecione uma listagem e altere o nome/período do oficial. As mudanças ficam salvas localmente.").pack(anchor="w",pady=(0,8))
        cols=("listing","official","period"); tree=ttk.Treeview(tab1,columns=cols,show="headings",height=13)
        for c,label,w in (("listing","Listagem",100),("official","Oficial",260),("period","Período / observação",300)): tree.heading(c,text=label); tree.column(c,width=w)
        tree.pack(fill="both",expand=True)
        adj=self.adjustments.get("oficiais",{})
        for key in sorted(set(self.officials)|set(adj),key=lambda x:(not x.isdigit(),int(x) if x.isdigit() else x)):
            base=self.officials.get(str(key),{}); override=adj.get(str(key),{})
            if isinstance(override,str): override={"nome":override}
            tree.insert("","end",iid=str(key),values=(key,override.get("nome",base.get("nome","")),override.get("periodo",base.get("periodo",""))))
        def edit_official():
            sel=tree.selection()
            if not sel: messagebox.showinfo("Oficial","Selecione uma listagem.",parent=win); return
            key=sel[0]; vals=tree.item(key,"values")
            name=simpledialog.askstring("Nome do oficial",f"Oficial da listagem {key}:",initialvalue=vals[1],parent=win)
            if name is None:return
            period=simpledialog.askstring("Período / observação", "Período ou observação (pode deixar em branco):",initialvalue=vals[2],parent=win)
            if period is None:return
            tree.item(key,values=(key,name.strip(),period.strip()))
        ttk.Button(tab1,text="Editar oficial selecionado",command=edit_official).pack(anchor="w",pady=(8,0))
        # Tab areas
        tab2=ttk.Frame(book,padding=10); book.add(tab2,text="Áreas e registros de ruas")
        ttk.Label(tab2,text="Edite a área de um registro específico. O número da linha identifica o registro no arquivo original.").pack(anchor="w",pady=(0,8))
        recs=parse_records(self.adjustments); cols2=("line","listing","street","area"); t2=ttk.Treeview(tab2,columns=cols2,show="headings",height=13)
        for c,label,w in (("line","Linha",70),("listing","Listagem",80),("street","Rua/registro",330),("area","Bairro / Área",300)): t2.heading(c,text=label); t2.column(c,width=w)
        t2.pack(fill="both",expand=True)
        for r in recs: t2.insert("","end",iid=str(r["line"]),values=(r["line"],r["listing"],r["clean_name"],r["area"]))
        def edit_area():
            sel=t2.selection()
            if not sel: messagebox.showinfo("Área","Selecione um registro.",parent=win); return
            key=sel[0]; vals=t2.item(key,"values")
            area=simpledialog.askstring("Área",f"Nova área para {vals[2]} (listagem {vals[1]}):",initialvalue=vals[3],parent=win)
            if area is not None: t2.set(key,"area",area.strip())
        ttk.Button(tab2,text="Editar área selecionada",command=edit_area).pack(anchor="w",pady=(8,0))
        def save_all():
            current=load_adjustments(); current.setdefault("oficiais",{}); current.setdefault("areas",{})
            for key in tree.get_children():
                vals=tree.item(key,"values"); base=self.officials.get(str(key),{})
                if vals[1].strip()!=base.get("nome","") or vals[2].strip()!=base.get("periodo",""):
                    current["oficiais"][str(key)]={"nome":vals[1].strip(),"periodo":vals[2].strip()}
                else: current["oficiais"].pop(str(key),None)
            # Preserve area adjustments only when changed from the original source.
            original={r["line"]:r["area"] for r in parse_records({"areas":{},"oficiais":{}})}
            for key in t2.get_children():
                vals=t2.item(key,"values"); line=int(key); area=vals[3].strip()
                if area!=original.get(line,"Não especificada no arquivo"): current["areas"][str(line)]=area
                else: current["areas"].pop(str(line),None)
            save_adjustments(current); self.adjustments=current; self.records=parse_records(current)
            messagebox.showinfo("Dados salvos","Alterações salvas nesta pasta. Elas serão usadas nas próximas consultas.",parent=win)
            win.destroy()
        ttk.Button(win,text="Salvar alterações",command=save_all).pack(pady=(0,10))

    def show_folder(self): messagebox.showinfo("Pasta do programa","Arquivos de dados, ajustes e relatório ficam em:\n\n"+BASE_DIR)
    def clear(self):
        self.query.set(""); self.status.configure(text="Pronto para consultar."); self.set_note("Digite um endereço e clique em Consultar.")
        for i in self.tree.get_children(): self.tree.delete(i)
        self.last_result=None
        self._refresh_results()

if __name__=="__main__":
    App().mainloop()
