"""Motor de síntesis de voz, pronunciación y drills fonéticos para inglés técnico."""

import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# Diccionario de transcripción fonética IPA para colocaciones técnicas comunes en BI/IA
IPA_TECHNICAL_DICTIONARY: Dict[str, str] = {
    "trade-off": "/ˈtreɪd.ɒf/",
    "trade-offs": "/ˈtreɪd.ɒfs/",
    "bottleneck": "/ˈbɒt.əl.nek/",
    "bottlenecks": "/ˈbɒt.əl.neks/",
    "stakeholder": "/ˈsteɪkˌhoʊl.dɚ/",
    "stakeholders": "/ˈsteɪkˌhoʊl.dɚz/",
    "pipeline": "/ˈpaɪp.laɪn/",
    "pipelines": "/ˈpaɪp.laɪnz/",
    "throughput": "/ˈθruː.pʊt/",
    "latency": "/ˈleɪ.tən.si/",
    "query": "/ˈkwɪə.ri/",
    "queries": "/ˈkwɪə.riz/",
    "schema": "/ˈskiː.mə/",
    "schemas": "/ˈskiː.məz/",
    "dataset": "/ˈdeɪ.təˌset/",
    "datasets": "/ˈdeɪ.təˌsets/",
    "benchmark": "/ˈbentʃ.mɑːk/",
    "benchmarks": "/ˈbentʃ.mɑːks/",
    "deploy": "/dɪˈplɔɪ/",
    "deployment": "/dɪˈplɔɪ.mənt/",
    "scrum": "/skrʌm/",
    "sprint": "/sprɪnt/",
    "retrospective": "/ˌret.rəˈspek.tɪv/",
    "refactor": "/riːˈfæk.tər/",
    "idempotent": "/aɪˈdem.pə.tənt/",
    "clustering": "/ˈklʌs.tər.ɪŋ/",
    "partitioning": "/pɑːˈtɪʃ.ən.ɪŋ/",
    "transformer": "/trænsˈfɔː.mər/",
    "attention": "/əˈten.ʃən/",
    "deadline": "/ˈded.laɪn/",
    "blocker": "/ˈblɒk.ər/",
    "standup": "/ˈstænd.ʌp/",
    "clarify": "/ˈklær.ɪ.faɪ/",
    "recommendation": "/ˌrek.ə.menˈdeɪ.ʃən/",
    "consulting": "/kənˈsʌl.tɪŋ/",
    "roi": "/ˌɑːr.oʊˈaɪ/",
    "bandwidth": "/ˈbænd.wɪtθ/",
    "feasibility": "/ˌfiː.zəˈbɪl.ə.ti/",
    "milestone": "/ˈmaɪl.stoʊn/",
    "adoption": "/əˈdɑːp.ʃən/",
    "transformation": "/ˌtræns.fəˈmeɪ.ʃən/",
}


class SpeechRequest(BaseModel):
    """Petición de audio y pronunciación de un término o colocación técnica."""
    text: str = Field(..., description="Texto o colocación en inglés a vocalizar")
    accent: str = Field("en-US", description="Acento: 'en-US' o 'en-GB'")
    speed: float = Field(1.0, ge=0.5, le=2.0, description="Velocidad: 0.75, 1.0, 1.25")


class SpeechResponse(BaseModel):
    """Respuesta con metadatos de audio, guía fonética y método de reproducción."""
    text: str
    accent: str
    speed: float
    phonetic_guide: str
    method: str
    audio_base64: Optional[str] = None


class PronunciationRequest(BaseModel):
    """Petición de evaluación de pronunciación comparando texto hablado vs esperado."""
    expected_text: str = Field(default="", description="Texto o colocación esperada")
    spoken_text: str = Field(default="", description="Texto reconocido por el micrófono")
    expected: Optional[str] = None
    spoken: Optional[str] = None
    accent: str = Field("en-US", description="Acento objetivo ('en-US' o 'en-GB')")

    def model_post_init(self, __context: Any) -> None:
        if self.expected and not self.expected_text:
            self.expected_text = self.expected
        if self.spoken and not self.spoken_text:
            self.spoken_text = self.spoken


class PronunciationEvaluation(BaseModel):
    """Resultado del análisis fonético y léxico de lo pronunciado."""
    expected_text: str
    spoken_text: str
    accuracy_pct: float
    accuracy_score: float = 0.0
    verdict: str  # Excelente, Buena, Comprensible, Inexacto
    suggested_rating: int  # 1 (Again), 2 (Hard), 3 (Good), 4 (Easy)
    matched_words: List[str]
    missing_words: List[str]
    feedback_tip: str
    phonetic_guide: str


CONTRACTIONS: Dict[str, str] = {
    "i'm": "i am", "you're": "you are", "he's": "he is", "she's": "she is",
    "it's": "it is", "we're": "we are", "they're": "they are", "can't": "cannot",
    "don't": "do not", "doesn't": "does not", "didn't": "did not", "won't": "will not",
    "wouldn't": "would not", "couldn't": "could not", "shouldn't": "should not",
    "that's": "that is", "what's": "what is", "where's": "where is", "let's": "let us",
    "could've": "could have", "should've": "should have", "would've": "would have",
    "we've": "we have", "they've": "they have", "i've": "i have", "you've": "you have",
    "they'll": "they will", "we'll": "we will", "i'll": "i will", "you'll": "you will",
    "he'll": "he will", "she'll": "she will", "it'll": "it will",
}


def normalize_speech_text(text: str) -> str:
    """Normaliza texto expandiendo contracciones, guiones y signos de puntuación."""
    t = text.lower().strip()
    for contraction, expanded in CONTRACTIONS.items():
        t = re.sub(r"\b" + re.escape(contraction) + r"\b", expanded, t)
    # Convertir guiones en espacios (ej. high-severity -> high severity)
    t = re.sub(r"[\-]", " ", t)
    # Remover signos de puntuación restantes
    t = re.sub(r"[^\w\s]", "", t)
    # Normalizar espacios
    return re.sub(r"\s+", " ", t).strip()


class TTSEngine:
    """Motor de síntesis vocal y análisis fonético para FSRS."""

    def __init__(self):
        self.supported_accents = [
            {"code": "en-US", "name": "Inglés Americano (US)", "flag": "🇺🇸"},
            {"code": "en-GB", "name": "Inglés Británico (UK)", "flag": "🇬🇧"},
        ]
        self.supported_speeds = [0.75, 1.0, 1.25]

    def get_phonetic_guide(self, text: str) -> str:
        """Genera una guía fonética en notación IPA aproximada para las palabras de la colocación."""
        words = re.findall(r"[a-zA-Z\-]+", text.lower())
        phonetics = []

        for w in words:
            if w in IPA_TECHNICAL_DICTIONARY:
                phonetics.append(f"{w} {IPA_TECHNICAL_DICTIONARY[w]}")

        if phonetics:
            return " • ".join(phonetics)

        # Fallback de aproximación silábica
        return f"/{text.lower().replace(' ', ' · ')}/"

    def synthesize(self, req: SpeechRequest) -> SpeechResponse:
        """Genera la respuesta de pronunciación con metadatos para reproducción."""
        phonetic = self.get_phonetic_guide(req.text)

        return SpeechResponse(
            text=req.text,
            accent=req.accent if req.accent in ("en-US", "en-GB") else "en-US",
            speed=req.speed,
            phonetic_guide=phonetic,
            method="web_speech_api_preferred",
            audio_base64=None,
        )

    def evaluate_pronunciation(self, req: PronunciationRequest) -> PronunciationEvaluation:
        """Evalúa la coincidencia léxica y fonética entre lo dicho y lo esperado."""
        from difflib import SequenceMatcher

        norm_expected = normalize_speech_text(req.expected_text)
        norm_spoken = normalize_speech_text(req.spoken_text)

        exp_tokens = norm_expected.split()
        spk_tokens = norm_spoken.split()

        # Coincidencia de secuencia
        matcher = SequenceMatcher(None, exp_tokens, spk_tokens)
        ratio = matcher.ratio()

        # Tokens coincidentes y omitidos
        spk_set = set(spk_tokens)
        matched = [t for t in exp_tokens if t in spk_set]
        missing = [t for t in exp_tokens if t not in spk_set]

        accuracy = round(ratio * 100.0, 1)

        # Si no dijo nada
        if not norm_spoken:
            return PronunciationEvaluation(
                expected_text=req.expected_text,
                spoken_text="",
                accuracy_pct=0.0,
                accuracy_score=0.0,
                verdict="Sin Audio Detectado",
                suggested_rating=1,
                matched_words=[],
                missing_words=exp_tokens,
                feedback_tip="No se detectó audio en el micrófono. Vuelve a intentarlo.",
                phonetic_guide=self.get_phonetic_guide(req.expected_text),
            )

        if accuracy >= 88.0:
            verdict = "Excelente Pronunciación"
            suggested_rating = 4  # Easy
            feedback_tip = "¡Dicción y articulación fluidas! Dominaste esta colocación técnica."
        elif accuracy >= 70.0:
            verdict = "Buena Pronunciación"
            suggested_rating = 3  # Good
            feedback_tip = f"Pronunciación clara y comprensible. Cuidado con: {', '.join(missing[:3])}." if missing else "Buena pronunciación profesional."
        elif accuracy >= 45.0:
            verdict = "Comprensible con Desvíos"
            suggested_rating = 2  # Hard
            feedback_tip = f"Se entendió la idea general, pero omitiste o desviaste: {', '.join(missing[:4])}."
        else:
            verdict = "Inexacto / Requiere Repetir"
            suggested_rating = 1  # Again
            feedback_tip = "Desvío significativo respecto a la colocación esperada. Repite escuchando el audio modelo."

        phonetic = self.get_phonetic_guide(req.expected_text)

        return PronunciationEvaluation(
            expected_text=req.expected_text,
            spoken_text=req.spoken_text,
            accuracy_pct=accuracy,
            accuracy_score=accuracy,
            verdict=verdict,
            suggested_rating=suggested_rating,
            matched_words=matched,
            missing_words=missing,
            feedback_tip=feedback_tip,
            phonetic_guide=phonetic,
        )

    def get_config(self) -> Dict[str, Any]:
        """Retorna la configuración y capacidades del motor de audio."""
        return {
            "supported_accents": self.supported_accents,
            "supported_speeds": self.supported_speeds,
            "default_accent": "en-US",
            "default_speed": 1.0,
            "client_driver": "Web Speech API (speechSynthesis & SpeechRecognition)",
            "listening_shadowing_supported": True,
            "speech_recognition_supported": True,
        }
