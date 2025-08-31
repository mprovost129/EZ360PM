from django.contrib.auth.tokens import PasswordResetTokenGenerator

class EmailVerificationTokenGenerator(PasswordResetTokenGenerator):
    def _make_hash_value(self, user, timestamp):
        # changes when user verifies
        return f"{user.pk}{timestamp}{user.is_verified}" # type: ignore

email_verification_token = EmailVerificationTokenGenerator()
