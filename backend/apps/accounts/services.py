from django.core.mail import send_mail
from django.core.signing import TimestampSigner
from django.template.loader import render_to_string
from django.urls import reverse


def send_confirmation_email(request, user):
    """Sign the user PK and email a confirmation link."""
    signer = TimestampSigner()
    token = signer.sign(user.pk)

    confirm_url = request.build_absolute_uri(
        reverse("accounts:confirm_email", kwargs={"token": token})
    )

    subject = render_to_string(
        "accounts/email/confirm_email_subject.txt",
        {"user": user},
    ).strip()

    body = render_to_string(
        "accounts/email/confirm_email.txt",
        {"user": user, "confirm_url": confirm_url},
    )

    send_mail(
        subject=subject,
        message=body,
        from_email=None,  # uses DEFAULT_FROM_EMAIL
        recipient_list=[user.email],
        fail_silently=False,
    )
