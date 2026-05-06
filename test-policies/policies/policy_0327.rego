package audit.authentication.context.verify.utils.policy_0327

# Auto-generated policy 327 (Rego v1 syntax)
# Package: audit.authentication.context.verify.utils

# Metadata
metadata := {
    "policy_id": "0327",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0327_allowed if {
    data.policies.audit.enabled
}
policy_0327_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0327_allowed if {
    input.user.role == "admin"
}
default policy_0327_allowed = false
