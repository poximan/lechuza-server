import re

import requests


_SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class ArtifactReleaseClient:
    """Traduce el contrato HTTP del repositorio al contrato RPC de Panelito."""

    def __init__(self, release_url: str, apk_url: str, app_name: str, timeout_seconds: int):
        self._release_url = release_url
        self._apk_url = apk_url
        self._app_name = app_name
        self._timeout_seconds = timeout_seconds

    def current_release(self, installed_version_code: int) -> dict:
        if type(installed_version_code) is not int or installed_version_code <= 0:
            raise ValueError("current_version_code invalido")
        response = requests.get(
            self._release_url,
            headers={"Accept": "application/json"},
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        release = response.json()
        if not isinstance(release, dict) or release.get("contractVersion") != 1:
            raise RuntimeError("Contrato de artifact-repository invalido")
        if release.get("appName") != self._app_name:
            raise RuntimeError("artifact-repository devolvio otra aplicacion")
        if release.get("apkPath") != f"/repo/{self._app_name}/app.apk":
            raise RuntimeError("artifact-repository devolvio una ruta APK invalida")
        if release.get("hashAlgorithm") != "sha256":
            raise RuntimeError("artifact-repository devolvio un algoritmo invalido")

        version_name = str(release.get("appVersion") or "").strip()
        content_hash = str(release.get("contentHash") or "").strip().lower()
        version_code = release.get("versionCode")
        size_bytes = release.get("sizeBytes")
        max_omissions = release.get("maxOmissions")
        if not version_name:
            raise RuntimeError("artifact-repository no informo versionName")
        if type(version_code) is not int or version_code <= 0:
            raise RuntimeError("artifact-repository informo versionCode invalido")
        if type(size_bytes) is not int or size_bytes <= 0:
            raise RuntimeError("artifact-repository informo sizeBytes invalido")
        if type(max_omissions) is not int or max_omissions < 0:
            raise RuntimeError("artifact-repository informo maxOmissions invalido")
        if _SHA256_PATTERN.fullmatch(content_hash) is None:
            raise RuntimeError("artifact-repository informo SHA-256 invalido")

        return {
            "contract_version": 1,
            "app": self._app_name,
            "platform": "android",
            "latest_version": version_name,
            "artifact_version_code": version_code,
            "artifact_size_bytes": size_bytes,
            "hash_algorithm": "sha256",
            "artifact_hash": content_hash,
            "apk_url": self._apk_url,
            "max_omissions": max_omissions,
            "update_required": version_code > installed_version_code,
        }
