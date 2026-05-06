package compliance.authorization.resource.allow.helpers.policy_0025

# Auto-generated policy 25 (Rego v1 syntax)
# Package: compliance.authorization.resource.allow.helpers

# Metadata
metadata := {
    "policy_id": "0025",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0025_allowed if {
    input.user.role == "admin"
}
policy_0025_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0025_allowed = false
