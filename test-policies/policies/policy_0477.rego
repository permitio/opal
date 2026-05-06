package security.enforcement.context.check.utils.policy_0477

# Auto-generated policy 477 (Rego v1 syntax)
# Package: security.enforcement.context.check.utils

# Metadata
metadata := {
    "policy_id": "0477",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0477_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0477_allowed if {
    input.user.active
    input.resource.public
}
