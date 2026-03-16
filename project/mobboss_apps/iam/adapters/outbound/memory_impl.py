"""Memory-mode IAM outbound adapter implementation."""

from project.mobboss_apps.iam.adapters.outbound.django_auth_impl import DjangoIamOutboundPortImpl


class MemoryIamOutboundPortImpl(DjangoIamOutboundPortImpl):
    """Memory-mode alias for IAM auth gateway."""

