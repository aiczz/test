"""验证码下发通道。

目前两种后端：

- ``console``（默认）：只把验证码打到服务日志。机制是真的、码也是随机生成的，
  只是没真发出去 —— 零配置就能跑，适合开发和没配邮箱时兜底。
- ``smtp``：真的发邮件。需要把 ``SMTP_*`` 配全（邮箱的「SMTP 授权码」，
  不是登录密码）。

要接短信的话，在这里加一个分支即可：业务代码只认 ``send_code`` 这个函数，
换通道不用动验证码逻辑。
"""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


class MailError(RuntimeError):
    """发信失败。调用方负责把它转成对用户友好的提示。"""


def send_code(*, target: str, code: str, purpose: str) -> str:
    """把验证码发给 target，返回实际使用的通道名。"""
    if settings.mail_backend == "smtp":
        _send_smtp(target=target, code=code, purpose=purpose)
        return "smtp"

    minutes = max(settings.code_ttl_seconds // 60, 1)
    # 用 warning 级别：默认日志配置下 INFO 常常被过滤掉，而这个必须能看见。
    logger.warning(
        "[验证码] mail_backend=console，没有真发信。target=%s code=%s（%s 分钟内有效）",
        target,
        code,
        minutes,
    )
    return "console"


def _send_smtp(*, target: str, code: str, purpose: str) -> None:
    if not (settings.smtp_host and settings.smtp_user and settings.smtp_password):
        raise MailError(
            "SMTP 没配全：需要 smtp_host / smtp_user / smtp_password（授权码）"
        )

    action = "注册" if purpose == "register" else "登录"
    minutes = max(settings.code_ttl_seconds // 60, 1)

    message = EmailMessage()
    message["Subject"] = f"【食时】{action}验证码 {code}"
    message["From"] = settings.smtp_from or settings.smtp_user
    message["To"] = target
    message.set_content(
        f"你的{action}验证码是：{code}\n\n"
        f"{minutes} 分钟内有效。请勿转发给他人。\n"
        f"如果不是你本人操作，忽略这封邮件即可。\n\n"
        f"—— 食时（AI 时令饮食助手）"
    )

    try:
        if settings.smtp_ssl:
            with smtplib.SMTP_SSL(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout,
            ) as server:
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(message)
        else:
            with smtplib.SMTP(
                settings.smtp_host,
                settings.smtp_port,
                timeout=settings.smtp_timeout,
            ) as server:
                server.starttls()
                server.login(settings.smtp_user, settings.smtp_password)
                server.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        raise MailError(f"邮件发送失败：{exc}") from exc
