from __future__ import annotations

from dataclasses import dataclass

SUPPORTED_LANGUAGES = {"go", "ts", "py", "rs", "php"}


@dataclass(frozen=True)
class HandlerSpec:
    vendor: str
    app: str
    language: str
    scheme: str
    app_path: str
    instance: str = ""
    version: str = ""
    channel: str = ""
    display_name: str = ""

    @classmethod
    def from_mapping(cls, value: dict[str, object]) -> "HandlerSpec":
        return cls(
            vendor=str(value.get("vendor", "")),
            app=str(value.get("app", "")),
            instance=str(value.get("instance", "")),
            language=str(value.get("language", "")),
            scheme=str(value.get("scheme", "")),
            version=str(value.get("version", "")),
            channel=str(value.get("channel", "")),
            app_path=str(value.get("appPath", value.get("app_path", ""))),
            display_name=str(value.get("displayName", value.get("display_name", ""))),
        )

    def validate(self) -> None:
        required = {
            "vendor": self.vendor,
            "app": self.app,
            "language": self.language,
            "scheme": self.scheme,
            "app_path": self.app_path,
        }
        for field, value in required.items():
            if not value:
                raise ValueError(f"generate: {field} must not be empty")

        if self.language not in SUPPORTED_LANGUAGES:
            raise ValueError(f"generate: unsupported language {self.language!r}")

        for field, value in {
            "vendor": self.vendor,
            "app": self.app,
            "instance": self.instance,
            "language": self.language,
            "scheme": self.scheme,
        }.items():
            if "/" in value or "\\" in value:
                raise ValueError(f"generate: {field} must not contain path separators")

    def handler_id(self) -> str:
        self.validate()
        parts = [self.vendor, self.app]
        if self.instance:
            parts.append(self.instance)
        parts.extend([self.language, self.scheme])
        return ".".join(parts)

    def resolved_display_name(self) -> str:
        if self.display_name:
            return self.display_name
        try:
            return self.handler_id()
        except ValueError:
            return self.app


def desktop_file(spec: HandlerSpec) -> str:
    handler_id = spec.handler_id()
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={spec.resolved_display_name()}\n"
        f"Exec={spec.app_path} %u\n"
        f"MimeType=x-scheme-handler/{spec.scheme};\n"
        "NoDisplay=true\n"
        f"X-Hop-Handler-ID={handler_id}\n"
    )


def desktop_filename(spec: HandlerSpec) -> str:
    return spec.handler_id() + ".desktop"


def plist_snippet(spec: HandlerSpec) -> str:
    handler_id = spec.handler_id()
    return (
        "<key>CFBundleURLTypes</key>\n"
        "<array>\n"
        "\t<dict>\n"
        "\t\t<key>CFBundleURLName</key>\n"
        f"\t\t<string>{handler_id}</string>\n"
        "\t\t<key>CFBundleURLSchemes</key>\n"
        "\t\t<array>\n"
        f"\t\t\t<string>{spec.scheme}</string>\n"
        "\t\t</array>\n"
        "\t</dict>\n"
        "</array>"
    )


def patch_plist(source: str, spec: HandlerSpec) -> str:
    spec.validate()
    snippet = plist_snippet(spec)
    replaced = source.replace("</dict>\n</plist>", snippet + "\n</dict>\n</plist>", 1)
    if replaced != source:
        return replaced
    return source.replace("</dict></plist>", snippet + "\n</dict></plist>", 1)


def windows_reg_snippet(spec: HandlerSpec) -> str:
    handler_id = spec.handler_id()
    display_name = spec.resolved_display_name()
    return (
        "Windows Registry Editor Version 5.00\r\n\r\n"
        f"[HKEY_CURRENT_USER\\Software\\Classes\\{spec.scheme}]\r\n"
        f"@=\"URL:{display_name} Protocol\"\r\n"
        "\"URL Protocol\"=\"\"\r\n"
        f"\"FriendlyTypeName\"=\"{display_name}\"\r\n"
        f"\"HopHandlerID\"=\"{handler_id}\"\r\n\r\n"
        f"[HKEY_CURRENT_USER\\Software\\Classes\\{spec.scheme}\\shell\\open\\command]\r\n"
        f"@=\"\\\"{spec.app_path}\\\" \\\"%1\\\"\"\r\n"
    )


def snippet(platform: str, spec: HandlerSpec) -> str:
    if platform in {"macos", "ios"}:
        return plist_snippet(spec)
    if platform == "linux":
        return desktop_file(spec)
    if platform == "windows":
        return windows_reg_snippet(spec)
    raise ValueError(f"generate: unknown platform {platform!r}")
