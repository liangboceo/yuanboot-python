"""Framework identity shared by startup logs and API documentation."""

from yuanboot._version import __version__

PROJECT_URL = "https://github.com/liangboceo/yuanboot-python"
DOCUMENTATION_URL = "https://yuanboot.star2cloud.com/python/"
COPYRIGHT = "Copyright (c) 2019 max zhang; Copyright (c) 2026 yuanboot contributors"
NOTICE = f"yuanboot-python {__version__} | {COPYRIGHT} | MIT License"


def swagger_description(description: str | None = None) -> str:
    return (description or "").rstrip() + (
        f"\n\n---\nPowered by [yuanboot-python {__version__}]({PROJECT_URL}).\n\n"
        f"{COPYRIGHT}. [MIT License](https://opensource.org/licenses/MIT)."
    )
