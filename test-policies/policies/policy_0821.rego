package compliance.authorization.action.check.utils.policy_0821

# Auto-generated policy 821 (Rego v1 syntax)
# Package: compliance.authorization.action.check.utils

# Metadata
metadata := {
    "policy_id": "0821",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0821_allowed if {
    input.user.active
    input.resource.public
}
policy_0821_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
