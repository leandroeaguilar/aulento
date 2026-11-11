"""Conector y sincronizador de perfil y racha con la API pública de Duolingo."""

import json
import sqlite3
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel, Field

from aulento.core.secretos import AJUSTE_DUOLINGO_CACHE, AJUSTE_DUOLINGO_USUARIO, AjustesDeCuenta

MENSAJE_SIN_USUARIO = (
    "Falta configurar tu usuario de Duolingo: indicalo en la sincronización o con "
    "'aulento duolingo set-user <usuario>'."
)
ESTADO_SIN_CONFIGURAR = "sin_configurar"


class DuolingoSinConfigurar(RuntimeError):
    """La cuenta no tiene un usuario de Duolingo configurado: no hay a quién consultar."""

    def __init__(self) -> None:
        super().__init__(MENSAJE_SIN_USUARIO)


class DuolingoCourse(BaseModel):
    id: str = ""
    title: str = "English"
    learning_language: str = "en"
    from_language: str = "es"
    xp: int = 0
    crowns: int = 0


class DuolingoProfile(BaseModel):
    username: str
    name: str = ""
    streak: int = 0
    total_xp: int = 0
    learning_language: str = "en"
    current_course_title: str = "English"
    streak_start_date: Optional[str] = None
    streak_end_date: Optional[str] = None
    has_recent_activity: bool = False
    cached_at: Optional[str] = None
    is_cached: bool = False
    courses: List[DuolingoCourse] = Field(default_factory=list)


class DuolingoSyncResult(BaseModel):
    status: str  # ok, cached, error, sin_configurar
    username: str
    streak: int
    total_xp: int
    source: str  # live, cache
    message: str
    updated_at: str


class DuolingoClient:
    """Consulta la racha y las estadísticas del usuario de Duolingo de una cuenta.

    El usuario y la caché del último perfil son ajustes de la cuenta; sin usuario configurado no consulta nada.
    """

    BASE_URL = "https://www.duolingo.com/2017-06-30/users"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    def __init__(self, conn: sqlite3.Connection, user_id: int, timeout: int = 8):
        self.ajustes = AjustesDeCuenta(conn, user_id)
        self.user_id = self.ajustes.user_id
        self.timeout = timeout

    def usuario_configurado(self) -> Optional[str]:
        """Usuario de Duolingo de la cuenta, o None si no configuró ninguno."""
        guardado = self.ajustes.leer(AJUSTE_DUOLINGO_USUARIO)
        return guardado if isinstance(guardado, str) and guardado.strip() else None

    def fijar_usuario(self, username: Optional[str]) -> Optional[str]:
        """Guarda el usuario de Duolingo de la cuenta; vacío o None lo quita junto con su caché. Devuelve el vigente."""
        limpio = (username or "").strip().lower()
        if not limpio:
            self.ajustes.borrar(AJUSTE_DUOLINGO_USUARIO)
            self.ajustes.borrar(AJUSTE_DUOLINGO_CACHE)
            return None
        if limpio != self.usuario_configurado():
            self.ajustes.borrar(AJUSTE_DUOLINGO_CACHE)
        self.ajustes.guardar(AJUSTE_DUOLINGO_USUARIO, limpio)
        return limpio

    def _usuario_a_consultar(self, username: Optional[str]) -> str:
        """El usuario indicado o el de la cuenta; sin ninguno levanta `DuolingoSinConfigurar`."""
        limpio = (username or "").strip().lower() or self.usuario_configurado()
        if not limpio:
            raise DuolingoSinConfigurar()
        return limpio

    def _save_cache(self, profile: DuolingoProfile) -> None:
        """Guarda el perfil en los ajustes de la cuenta para resiliencia offline."""
        try:
            data = profile.model_dump()
            data["cached_at"] = datetime.now(timezone.utc).isoformat()
            self.ajustes.guardar(AJUSTE_DUOLINGO_CACHE, data)
        except Exception:
            pass  # Fallo silencioso de caché para no bloquear el flujo principal

    def _load_cache(self) -> Optional[DuolingoProfile]:
        """Carga el último perfil guardado en la caché de la cuenta, si existe."""
        try:
            data = self.ajustes.leer(AJUSTE_DUOLINGO_CACHE)
            if not isinstance(data, dict):
                return None
            return DuolingoProfile(**{**data, "is_cached": True})
        except Exception:
            return None

    def get_profile(self, username: Optional[str] = None, force_refresh: bool = False) -> DuolingoProfile:
        """Obtiene el perfil desde la API pública de Duolingo o desde la caché de la cuenta.

        Sin `username` consulta el usuario configurado; si la cuenta no tiene uno levanta
        `DuolingoSinConfigurar` sin hacer ninguna consulta.
        """
        clean_user = self._usuario_a_consultar(username)

        encoded_user = urllib.parse.quote(clean_user)
        url = f"{self.BASE_URL}?username={encoded_user}"
        req = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT})

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                content = response.read().decode("utf-8")
                payload = json.loads(content)

            users = payload.get("users", [])
            if not users:
                raise ValueError(f"Usuario de Duolingo '{clean_user}' no encontrado.")

            u = users[0]
            streak_data = u.get("streakData", {}).get("currentStreak", {})

            raw_courses = u.get("courses", [])
            courses = [
                DuolingoCourse(
                    id=str(c.get("id", "")),
                    title=c.get("title", "English"),
                    learning_language=c.get("learningLanguage", "en"),
                    from_language=c.get("fromLanguage", "es"),
                    xp=int(c.get("xp", 0)),
                    crowns=int(c.get("crowns", 0)),
                )
                for c in raw_courses
            ]

            profile = DuolingoProfile(
                username=u.get("username", clean_user),
                name=u.get("name") or clean_user,
                streak=int(u.get("streak", 0)),
                total_xp=int(u.get("totalXp", 0)),
                learning_language=u.get("learningLanguage", "en"),
                current_course_title="English" if not courses else courses[0].title,
                streak_start_date=streak_data.get("startDate"),
                streak_end_date=streak_data.get("endDate"),
                has_recent_activity=bool(u.get("hasRecentActivity15", False)),
                cached_at=datetime.now(timezone.utc).isoformat(),
                is_cached=False,
                courses=courses,
            )

            # La caché es la del usuario de la cuenta: una consulta puntual de otro usuario no la pisa
            if clean_user == self.usuario_configurado():
                self._save_cache(profile)
            return profile

        except Exception as e:
            # Fallback a la caché de la cuenta si la red falla o Duolingo no responde
            cached = self._load_cache()
            if cached and cached.username.lower() == clean_user:
                return cached

            raise RuntimeError(
                f"No se pudo consultar el perfil de Duolingo para '{clean_user}' ({e}) "
                "y no hay datos locales en caché."
            ) from e

    def sync(self, username: Optional[str] = None) -> DuolingoSyncResult:
        """Sincroniza y retorna un resumen del estado del usuario de Duolingo de la cuenta.

        Un `username` indicado pasa a ser el de la cuenta. Sin usuario responde `sin_configurar` sin consultar nada.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        if (username or "").strip():
            self.fijar_usuario(username)
        usuario = self.usuario_configurado()
        if usuario is None:
            return DuolingoSyncResult(
                status=ESTADO_SIN_CONFIGURAR,
                username="",
                streak=0,
                total_xp=0,
                source="none",
                message=MENSAJE_SIN_USUARIO,
                updated_at=now_iso,
            )
        try:
            profile = self.get_profile(force_refresh=True)
            source = "cache" if profile.is_cached else "live"
            status = "cached" if profile.is_cached else "ok"
            msg = f"Racha activa de {profile.streak} días y {profile.total_xp} XP acumulados."
            return DuolingoSyncResult(
                status=status,
                username=profile.username,
                streak=profile.streak,
                total_xp=profile.total_xp,
                source=source,
                message=msg,
                updated_at=now_iso,
            )
        except Exception as e:
            return DuolingoSyncResult(
                status="error",
                username=usuario,
                streak=0,
                total_xp=0,
                source="none",
                message=f"Error al sincronizar con Duolingo: {e}",
                updated_at=now_iso,
            )
