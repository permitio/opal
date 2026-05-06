package audit.authentication.policy.validate.utils.policy_0664

# Auto-generated policy 664 (Rego v1 syntax)
# Package: audit.authentication.policy.validate.utils

# Metadata
metadata := {
    "policy_id": "0664",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0664_allowed if {
    input.user.active
    input.resource.public
}
policy_0664_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
