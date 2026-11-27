"""한글 → 초성 · 자모 (자동완성용). es_reload.py 와 API 가 같은 규칙을 써야 함"""
CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'
JUNG = 'ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ'
JONG = ['', 'ㄱ', 'ㄲ', 'ㄳ', 'ㄴ', 'ㄵ', 'ㄶ', 'ㄷ', 'ㄹ', 'ㄺ', 'ㄻ', 'ㄼ', 'ㄽ', 'ㄾ', 'ㄿ', 'ㅀ', 'ㅁ', 'ㅂ', 'ㅄ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ']
# 겹받침 · 겹모음은 입력할 때 두 번 치므로 풀어 둠 (닭 → ㄷㅏㄹㄱ : '달' 까지 쳐도 맞게)
SPLIT = {'ㄳ': 'ㄱㅅ', 'ㄵ': 'ㄴㅈ', 'ㄶ': 'ㄴㅎ', 'ㄺ': 'ㄹㄱ', 'ㄻ': 'ㄹㅁ', 'ㄼ': 'ㄹㅂ', 'ㄽ': 'ㄹㅅ', 'ㄾ': 'ㄹㅌ', 'ㄿ': 'ㄹㅍ',
         'ㅀ': 'ㄹㅎ', 'ㅄ': 'ㅂㅅ', 'ㅘ': 'ㅗㅏ', 'ㅙ': 'ㅗㅐ', 'ㅚ': 'ㅗㅣ', 'ㅝ': 'ㅜㅓ', 'ㅞ': 'ㅜㅔ', 'ㅟ': 'ㅜㅣ', 'ㅢ': 'ㅡㅣ'}


def jamo(s: str) -> str:
    """김치ㅉ → ㄱㅣㅁㅊㅣㅉ (공백은 뺌)"""
    out = []
    for ch in s.replace(' ', ''):
        c = ord(ch) - 0xAC00
        if 0 <= c < 11172:
            parts = CHO[c // 588] + JUNG[(c % 588) // 28] + JONG[c % 28]
        else:
            parts = ch
        out.append(''.join(SPLIT.get(p, p) for p in parts))
    return ''.join(out).lower()


def chosung(s: str) -> str:
    """김치찌개 → ㄱㅊㅉㄱ (한글이 아닌 글자는 그대로)"""
    out = []
    for ch in s.replace(' ', ''):
        c = ord(ch) - 0xAC00
        out.append(CHO[c // 588] if 0 <= c < 11172 else ch)
    return ''.join(out).lower()


def is_chosung_only(s: str) -> bool:
    s = s.replace(' ', '')
    return bool(s) and all(ch in CHO for ch in s)