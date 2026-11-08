"""HH API adapter. Mutating operations require verified credentials and feature gate."""
import httpx

from .config import settings


class HHClient:
    def __init__(self):
        headers = {}
        if settings.hh_access_token:
            headers["Authorization"] = f"Bearer {settings.hh_access_token}"
        if settings.hh_user_agent:
            headers["HH-User-Agent"] = settings.hh_user_agent
        self.client = httpx.Client(
            base_url="https://api.hh.ru",
            headers=headers,
            timeout=20,
        )

    def search(self, text: str, page: int = 0) -> dict:
        response = self.client.get("/vacancies", params={"text": text, "page": page, "per_page": 100})
        response.raise_for_status()
        return response.json()

    def vacancy(self, hh_id: str) -> dict:
        response = self.client.get(f"/vacancies/{hh_id}")
        response.raise_for_status()
        return response.json()

    def applicant_negotiations(self) -> list[dict]:
        items = []
        page = 0
        while True:
            response = self.client.get("/negotiations", params={"per_page": 100, "page": page})
            response.raise_for_status()
            payload = response.json()
            if "items" not in payload or "pages" not in payload:
                raise RuntimeError("HH negotiation response cannot prove absence of an application")
            items.extend(payload["items"])
            page += 1
            if page >= payload["pages"]:
                return items

    def find_application(self, vacancy_id: str, resume_id: str) -> dict | None:
        for item in self.applicant_negotiations():
            if str((item.get("vacancy") or {}).get("id")) == vacancy_id and str((item.get("resume") or {}).get("id")) == resume_id:
                return item
        return None

    def apply(self, vacancy_id: str, resume_id: str, letter: str) -> dict:
        if not settings.hh_autonomy_enabled or not settings.hh_api_verified:
            raise RuntimeError("HH autonomous mutations require verified API access")
        response = self.client.post("/negotiations", data={"vacancy_id": vacancy_id, "resume_id": resume_id, "message": letter})
        response.raise_for_status()
        return response.json() if response.content else {}
