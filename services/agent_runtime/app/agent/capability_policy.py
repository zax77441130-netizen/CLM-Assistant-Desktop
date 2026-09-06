from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CapabilityDecision(str, Enum):
    AUTO = "AUTO"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    SESSION_ALLOWED = "SESSION_ALLOWED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class CapabilityRule:
    capability: str
    decision: CapabilityDecision
    reason: str


class CapabilityPolicy:
    RULES: dict[str, CapabilityRule] = {
        "workspace.read": CapabilityRule("workspace.read", CapabilityDecision.AUTO, "一般工作區讀取可自動執行。"),
        "workspace.write": CapabilityRule("workspace.write", CapabilityDecision.AUTO, "工作區內可 Undo 的低風險寫入可自動執行。"),
        "archive.create": CapabilityRule("archive.create", CapabilityDecision.AUTO, "建立新 ZIP 不覆寫既有檔案。"),
        "archive.extract": CapabilityRule("archive.extract", CapabilityDecision.APPROVAL_REQUIRED, "解壓縮會建立多個檔案，需要核准。"),
        "recovery_bin.write": CapabilityRule("recovery_bin.write", CapabilityDecision.APPROVAL_REQUIRED, "移至助理回收區屬於大量或破壞性整理。"),
        "recovery_bin.restore": CapabilityRule("recovery_bin.restore", CapabilityDecision.AUTO, "不覆寫既有檔案的恢復可自動執行。"),
        "host.open_file": CapabilityRule("host.open_file", CapabilityDecision.AUTO, "只能開啟工作區內非可執行檔。"),
        "host.open_folder": CapabilityRule("host.open_folder", CapabilityDecision.AUTO, "只能開啟工作區內資料夾。"),
        "clipboard.read": CapabilityRule("clipboard.read", CapabilityDecision.APPROVAL_REQUIRED, "讀取剪貼簿需要使用者明確授權。"),
        "clipboard.write": CapabilityRule("clipboard.write", CapabilityDecision.AUTO, "使用者明確要求寫入剪貼簿時可自動執行。"),
        "process.terminate": CapabilityRule("process.terminate", CapabilityDecision.APPROVAL_REQUIRED, "終止程序屬高風險操作。"),
        "desktop.window.list": CapabilityRule("desktop.window.list", CapabilityDecision.AUTO, "列出一般視窗可自動執行。"),
        "desktop.window.activate": CapabilityRule("desktop.window.activate", CapabilityDecision.AUTO, "啟用已授權視窗可自動執行。"),
        "desktop.window.state": CapabilityRule("desktop.window.state", CapabilityDecision.AUTO, "調整已授權視窗狀態可自動執行。"),
        "desktop.control.inspect": CapabilityRule("desktop.control.inspect", CapabilityDecision.AUTO, "檢查基本控制項 metadata 可自動執行。"),
        "desktop.control.read": CapabilityRule("desktop.control.read", CapabilityDecision.APPROVAL_REQUIRED, "讀取視窗文字需要明確授權。"),
        "desktop.control.invoke": CapabilityRule("desktop.control.invoke", CapabilityDecision.APPROVAL_REQUIRED, "點擊控制項可能有外部副作用，需要核准。"),
        "desktop.control.write": CapabilityRule("desktop.control.write", CapabilityDecision.APPROVAL_REQUIRED, "寫入桌面應用程式內容需要核准。"),
        "desktop.window.close": CapabilityRule("desktop.window.close", CapabilityDecision.APPROVAL_REQUIRED, "關閉視窗可能造成未儲存內容遺失，需要核准。"),
        "desktop.screen.capture": CapabilityRule("desktop.screen.capture", CapabilityDecision.APPROVAL_REQUIRED, "擷取視窗畫面需要核准。"),
        "engineering.command.run": CapabilityRule("engineering.command.run", CapabilityDecision.APPROVAL_REQUIRED, "執行專案測試或建置腳本需要精確核准。"),
        "execution.arbitrary": CapabilityRule("execution.arbitrary", CapabilityDecision.BLOCKED, "任意命令與任意 executable path 永久禁止。"),
        "file.delete_permanent": CapabilityRule("file.delete_permanent", CapabilityDecision.BLOCKED, "永久刪除延後，且未來必須最高風險核准。"),
    }

    def decision_for(self, capability: str) -> CapabilityRule:
        return self.RULES.get(capability, CapabilityRule(capability, CapabilityDecision.BLOCKED, "未知能力已阻擋。"))
