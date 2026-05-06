package audit.authorization.context.check.utils.policy_0808

# Auto-generated policy 808
# Package: audit.authorization.context.check.utils

# Metadata
metadata := {
    "policy_id": "0808",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
allowed_0808 {
    input.user.role == "admin"
}
allowed_0808 {
    input.user.active
    input.resource.public
}
default allowed_0808 = false
allowed_0808 {
    data.policies.audit.enabled
}

# Utility function for user info
